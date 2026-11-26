"""The worker's job execution: start or continue a report's run, resume a pause (by text or by
voice), and on failure either try again or give up and tell the person."""

import asyncio
import logging
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langgraph.types import Command
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.execution_log import ExecutionLog
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.jobs import runner
from app.services.jobs.errors import PermanentJobError
from app.services.jobs.queue import RESUME, RUN, ClaimedJob, claim_next, enqueue
from app.services.jobs.runner import execute, process
from app.services.transcription import Transcript


class FakeGraph:
    def __init__(self, *, values: dict[str, Any] | None = None, next_nodes: tuple[str, ...] = (),
                 paused: bool = False, result: dict[str, Any] | None = None) -> None:
        tasks = [SimpleNamespace(interrupts=("pause",) if paused else ())]
        self.aget_state = AsyncMock(return_value=SimpleNamespace(values=values or {}, next=next_nodes, tasks=tasks))
        self.ainvoke = AsyncMock(return_value=result or {})


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(runner, "get_channel_adapter", lambda _connection: mock)
    return mock


@pytest.fixture
def checkpoints(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    deleter = AsyncMock()
    monkeypatch.setattr(runner, "get_checkpointer", lambda: SimpleNamespace(adelete_thread=deleter))
    return deleter


def _use_graph(monkeypatch: pytest.MonkeyPatch, graph: FakeGraph) -> FakeGraph:
    monkeypatch.setattr(runner, "get_compiled_graph", lambda: graph)
    return graph


async def _report(db: AsyncSession, *, language: str = "es", status: str = "pending") -> Report:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language=language, timezone="Europe/Madrid")
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id, channel_type="telegram", display_name="Bot",
        credentials={"bot_token": "t"}, allowed_senders=[], is_active=True,
    )
    db.add(connection)
    await db.flush()
    report = Report(
        tenant_id=tenant.id, status=status, requester_channel="telegram", requester_identifier="42",
        channel_connection_id=connection.id,
    )
    db.add(report)
    await db.commit()
    return report


def _job(report: Report, kind: str, payload: dict[str, Any], attempts: int = 1) -> ClaimedJob:
    return ClaimedJob(uuid.uuid4(), report.id, kind, payload, attempts, 3)


async def _queued(db: AsyncSession, report: Report, kind: str = RUN, **kwargs: Any) -> ClaimedJob:
    await enqueue(db, report_id=report.id, kind=kind, payload={"text": "hola"}, **kwargs)
    await db.commit()
    job = await claim_next("test-worker")
    assert job is not None
    return job


async def test_a_run_starts_the_graph_with_the_tenants_language_and_clock(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db, language="en")
    graph = _use_graph(monkeypatch, FakeGraph())

    await execute(_job(report, RUN, {"text": "Visited the site", "sender_label": "Ana"}))

    state = graph.ainvoke.await_args.args[0]
    assert (state.language, state.timezone, state.sender_label) == ("en", "Europe/Madrid", "Ana")
    assert (state.incoming_text, state.report_id, state.thread_id) == ("Visited the site", report.id, str(report.id))
    await db.refresh(report)
    assert report.source_text == "Visited the site"


async def test_a_report_in_its_own_language_is_read_in_it_not_in_the_company_s(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    # The landing's live demo: an English visitor in a Spanish company is transcribed, read and
    # rendered in English.
    report = await _report(db, language="es")
    report.channel_meta = {"public_demo": True, "locale": "en"}
    await db.commit()
    graph = _use_graph(monkeypatch, FakeGraph())

    await execute(_job(report, RUN, {"text": "Visited the site"}))

    assert graph.ainvoke.await_args.args[0].language == "en"


async def test_a_run_that_pauses_records_what_the_report_waits_for(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph(result={"__interrupt__": (SimpleNamespace(value={"kind": "confirm_report"}),)}))

    await execute(_job(report, RUN, {"text": "x"}))

    await db.refresh(report)
    assert report.status == "awaiting_approval"
    checkpoints.assert_not_awaited()  # a paused report will resume: keep its checkpoints


async def test_a_retry_carries_on_from_the_last_checkpoint(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(values={"transcript": "already paid for"}, next_nodes=("extract",)))

    await execute(_job(report, RUN, {"text": "x"}, attempts=2))

    assert graph.ainvoke.await_args.args[0] is None  # continue, don't start over


async def test_a_retry_of_a_run_that_already_finished_does_nothing(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(values={"done": True}, next_nodes=()))

    await execute(_job(report, RUN, {"text": "x"}, attempts=2))

    graph.ainvoke.assert_not_awaited()


async def test_a_resume_hands_the_reply_to_the_paused_graph(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db, status="pending")
    graph = _use_graph(monkeypatch, FakeGraph(paused=True))

    await execute(_job(report, RESUME, {"text": "la fecha era el martes"}))

    assert graph.ainvoke.await_args.args[0] == Command(resume="la fecha era el martes")


async def test_a_pressed_button_reaches_the_graph_as_a_structured_reply(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(paused=True))

    await execute(_job(report, RESUME, {"action": "doctype", "arg": "7f0c"}))

    assert graph.ainvoke.await_args.args[0] == Command(resume={"action": "doctype", "arg": "7f0c"})


async def test_a_voice_reply_is_transcribed_before_the_graph_sees_it(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(paused=True))
    adapter.download_media.return_value = b"opus"
    transcribe = AsyncMock(return_value=Transcript("  la fecha era el martes ", "whisper-large-v3-turbo"))
    monkeypatch.setattr(runner.transcription, "transcribe", transcribe)

    await execute(_job(report, RESUME, {"text": None, "media_reference": "voice-9"}))

    adapter.download_media.assert_awaited_once_with("voice-9")
    assert graph.ainvoke.await_args.args[0] == Command(resume="la fecha era el martes")
    assert transcribe.await_args.args[2] == "es"  # in the company's language


async def test_a_reply_said_and_typed_reaches_the_graph_whole(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(paused=True))
    adapter.download_media.return_value = b"opus"
    monkeypatch.setattr(runner.transcription, "transcribe", AsyncMock(return_value=Transcript("la fecha era el martes", "m")))

    await execute(_job(report, RESUME, {"text": "y el cliente es Norte", "media_reference": "voice-9"}))

    assert graph.ainvoke.await_args.args[0] == Command(resume="la fecha era el martes\n\ny el cliente es Norte")


async def test_a_voice_reply_is_metered_for_its_report(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph(paused=True))
    adapter.download_media.return_value = b"opus"
    transcribe = AsyncMock(return_value=Transcript("vale", "whisper-large-v3-turbo", 30.0))
    monkeypatch.setattr(runner.transcription, "transcribe", transcribe)

    await execute(_job(report, RESUME, {"text": None, "media_reference": "voice-9"}))

    [row] = (await db.execute(select(ExecutionLog))).scalars().all()
    assert (row.step, row.status, row.tenant_id, row.report_id) == ("transcribe_reply", "success", report.tenant_id, report.id)
    assert float(row.audio_seconds or 0) == 30.0
    assert float(row.cost_usd or 0) == pytest.approx(30 / 3600 * 0.04, abs=1e-6)
    assert transcribe.await_args.args[1].endswith(".ogg")  # a Telegram voice note is OGG Opus


async def test_a_resume_for_a_report_that_is_no_longer_paused_is_a_no_op(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(paused=False))

    await execute(_job(report, RESUME, {"text": "CONFIRM"}))

    graph.ainvoke.assert_not_awaited()  # an earlier attempt already delivered this answer


async def test_a_report_that_finished_loses_its_checkpoints(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db, status="delivered")
    _use_graph(monkeypatch, FakeGraph())

    await execute(_job(report, RUN, {"text": "x"}))

    checkpoints.assert_awaited_once_with(str(report.id))


async def test_a_job_that_succeeds_is_marked_done(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock
) -> None:
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph())
    job = await _queued(db, report)

    await process(job, "test-worker")

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "done"


async def test_a_failure_with_attempts_left_is_retried_and_the_report_is_left_alone(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph())
    graph.ainvoke.side_effect = TimeoutError()  # str(TimeoutError()) is empty: the log must still say something
    job = await _queued(db, report)

    await process(job, "test-worker")

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.last_error) == ("queued", "TimeoutError")
    await db.refresh(report)
    assert report.status == "pending"
    adapter.send_message.assert_not_awaited()


async def test_the_last_failure_fails_the_report_and_tells_the_person_in_their_language(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db, language="en")
    graph = _use_graph(monkeypatch, FakeGraph())
    graph.ainvoke.side_effect = RuntimeError("the provider is down")
    await enqueue(db, report_id=report.id, kind=RUN, payload={"text": "x"}, max_attempts=1)
    await db.commit()
    job = await claim_next("test-worker")
    assert job is not None

    await process(job, "test-worker")

    await db.refresh(report)
    assert report.status == "failed" and "the provider is down" in (report.error_detail or "")
    assert "couldn't generate" in adapter.send_message.await_args.args[0].text
    checkpoints.assert_awaited_once_with(str(report.id))


async def test_a_permanent_error_is_not_retried(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph())
    graph.ainvoke.side_effect = PermanentJobError("no active template")
    job = await _queued(db, report)

    await process(job, "test-worker")

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "failed"
    await db.refresh(report)
    assert report.status == "failed"


async def test_a_job_for_a_deleted_report_is_dropped_quietly(
    db: AsyncSession, own_sessions: None, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    await _queued(db, report)
    await db.delete(report)
    await db.commit()  # the FK cascades the job away too: nothing left to run

    assert await claim_next("test-worker") is None


# A graph step that runs long enough for the lease to be renewed (or lost) meanwhile, and
# records whether it was cancelled.
class SlowStep:
    def __init__(self, seconds: float, *, on_cancel: type[BaseException] = asyncio.CancelledError,
                 cleans_up_slowly: bool = False) -> None:
        self.seconds, self.on_cancel, self.cleans_up_slowly = seconds, on_cancel, cleans_up_slowly
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()

    async def run(self, *_args: Any) -> dict[str, Any]:
        self.started.set()
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError as exc:
            self.cancelled.set()
            if self.cleans_up_slowly:
                await asyncio.sleep(self.seconds)  # a window for something else to happen meanwhile
            # Some libraries turn a cancellation into an error of their own: that is no reason
            # to fail a job this worker no longer owns.
            raise self.on_cancel() from exc
        raise RuntimeError("the old worker finished after all")


@pytest.fixture
def quick_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Renew the lease every 400 ms instead of every 40 s: a real renewal here opens a session of
    its own and can take 150 ms, and it must end before two thirds of the lease are gone."""
    monkeypatch.setattr(runner, "LEASE_SECONDS", 1.2)


async def _taken_by_another_worker(db: AsyncSession, job: ClaimedJob) -> None:
    """What the claim does once this worker's lease has run out: the job is someone else's now."""
    await db.execute(update(Job).where(Job.id == job.id).values(locked_by="other-worker"))
    await db.commit()


@pytest.mark.parametrize("on_cancel", [asyncio.CancelledError, RuntimeError], ids=["cancelled", "cancel-as-error"])
async def test_a_lost_lease_stops_the_work_and_leaves_the_job_and_report_to_their_new_owner(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None, caplog: pytest.LogCaptureFixture, on_cancel: type[BaseException],
) -> None:
    report = await _report(db)
    step = SlowStep(2, on_cancel=on_cancel)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    # The last attempt: if this worker still did its bookkeeping, it would fail the report.
    job = await _queued(db, report, max_attempts=1)

    with caplog.at_level(logging.ERROR, logger="app.services.jobs.runner"):
        running = asyncio.create_task(process(job, "test-worker"))
        await asyncio.wait_for(step.started.wait(), timeout=5)
        await _taken_by_another_worker(db, job)
        await asyncio.wait_for(running, timeout=5)

    assert step.cancelled.is_set(), "the work in hand should be cancelled as soon as the lease is lost"
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by, stored.last_error) == ("running", "other-worker", None)
    await db.refresh(report)
    assert (report.status, report.error_detail) == ("pending", None)
    adapter.send_message.assert_not_awaited()
    checkpoints.assert_not_awaited()
    assert [r.getMessage() for r in caplog.records] == [f"Lost the lease on job {job.id}; another worker may have taken it"]


async def test_shutting_down_after_a_lost_lease_still_stops_the_worker(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None,
) -> None:
    report = await _report(db)
    step = SlowStep(10, cleans_up_slowly=True)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report)
    tasks_before = asyncio.all_tasks()
    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(step.started.wait(), timeout=5)
    await _taken_by_another_worker(db, job)
    await asyncio.wait_for(step.cancelled.wait(), timeout=5)  # the heartbeat cancelled the work...

    running.cancel()  # ...and the worker is told to stop while the work is still winding down
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(running, timeout=5)

    assert asyncio.all_tasks() == tasks_before
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by) == ("running", "other-worker")


@pytest.mark.parametrize("on_cancel", [asyncio.CancelledError, RuntimeError], ids=["cancelled", "cancel-as-error"])
async def test_a_lease_that_cannot_be_renewed_stops_the_work_and_the_worker(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None, on_cancel: type[BaseException],
) -> None:
    # Whether the lease is still held is unknown: nothing is recorded, and the worker stops (its
    # container restarts) so that the lease runs out and the job is claimed again.
    report = await _report(db)
    step = SlowStep(3, on_cancel=on_cancel)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report, max_attempts=1)

    async def unreachable_once_the_step_runs(*_args: Any) -> bool:
        await step.started.wait()
        raise ConnectionRefusedError("database unreachable")

    monkeypatch.setattr(runner, "extend_lease", unreachable_once_the_step_runs)
    tasks_before = asyncio.all_tasks()

    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(step.cancelled.wait(), timeout=2.5)  # promptly, not after the step or the time limit
    with pytest.raises(ConnectionRefusedError):
        await asyncio.wait_for(running, timeout=5)

    assert asyncio.all_tasks() == tasks_before
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by, stored.last_error) == ("running", "test-worker", None)
    await db.refresh(report)
    assert (report.status, report.error_detail) == ("pending", None)
    adapter.send_message.assert_not_awaited()
    checkpoints.assert_not_awaited()


@pytest.mark.parametrize("failure", ["refused", "hangs"])
async def test_renewals_that_keep_failing_stop_the_work_with_a_third_of_the_lease_left(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, failure: str,
) -> None:
    lease = 1.2  # as quick_lease, with the value at hand
    monkeypatch.setattr(runner, "LEASE_SECONDS", lease)
    report = await _report(db)
    step = SlowStep(5)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report, max_attempts=1)
    loop = asyncio.get_running_loop()
    renew, renewed_at = runner.extend_lease, loop.time()

    async def unreachable_once_the_step_runs(job_id: uuid.UUID, worker_id: str) -> bool:
        nonlocal renewed_at
        if not step.started.is_set():
            attempted_at = loop.time()
            held = await renew(job_id, worker_id)
            renewed_at = attempted_at
            return held
        if failure == "hangs":
            await asyncio.Event().wait()  # an unanswered socket: only a time limit ends it
        raise ConnectionRefusedError("database unreachable")

    monkeypatch.setattr(runner, "extend_lease", unreachable_once_the_step_runs)
    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(step.cancelled.wait(), timeout=5)
    cancelled_after = loop.time() - renewed_at
    with pytest.raises(TimeoutError if failure == "hangs" else ConnectionRefusedError):
        await asyncio.wait_for(running, timeout=5)

    # Retried after the first failure, and given up at two thirds of the lease, not at its end.
    assert lease / 2 < cancelled_after < lease * 2 / 3 + 0.05


async def test_a_database_blip_while_the_lease_still_holds_does_not_stop_the_work(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None, caplog: pytest.LogCaptureFixture,
) -> None:
    report = await _report(db)
    started = asyncio.Event()

    async def step(*_args: Any) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(2)  # cancelled, it raises CancelledError and the job isn't "done"
        return {}

    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step
    job = await _queued(db, report, max_attempts=1)
    renew = runner.extend_lease
    failed_once = False

    async def unreachable_once(job_id: uuid.UUID, worker_id: str) -> bool:
        nonlocal failed_once
        if started.is_set() and not failed_once:
            failed_once = True
            raise ConnectionRefusedError("database unreachable")
        return await renew(job_id, worker_id)

    monkeypatch.setattr(runner, "extend_lease", unreachable_once)
    with caplog.at_level(logging.WARNING, logger="app.services.jobs.runner"):
        await asyncio.wait_for(process(job, "test-worker"), timeout=5)

    assert failed_once
    assert [r.getMessage() for r in caplog.records if r.name == runner.logger.name] == [
        f"Couldn't renew the lease on job {job.id}; trying again"
    ]
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "done"


async def test_a_failure_after_an_unnoticed_takeover_leaves_the_job_and_report_to_their_new_owner(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, caplog: pytest.LogCaptureFixture,
) -> None:
    # The worker stalled past its lease and another took the job; the step fails before the next
    # heartbeat (every 40 s here) could notice. Last attempt: giving up would fail the report.
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = RuntimeError("the provider is down")
    job = await _queued(db, report, max_attempts=1)
    await _taken_by_another_worker(db, job)

    with caplog.at_level(logging.ERROR, logger="app.services.jobs.runner"):
        await asyncio.wait_for(process(job, "test-worker"), timeout=5)

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by, stored.last_error) == ("running", "other-worker", None)
    await db.refresh(report)
    assert (report.status, report.error_detail) == ("pending", None)
    adapter.send_message.assert_not_awaited()
    checkpoints.assert_not_awaited()
    taken = f"Job {job.id} was taken by another worker before this one could record its failure"
    assert [r.getMessage() for r in caplog.records].count(taken) == 1


async def test_a_failure_to_record_success_stops_the_worker_instead_of_failing_the_job(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock,
) -> None:
    # The work ended well; only its bookkeeping failed. That is no failure of the job to record
    # (nor to retry with backoff): the worker stops, and the job is claimed again once the lease
    # runs out, like any job of a worker that died.
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph())
    job = await _queued(db, report, max_attempts=1)
    monkeypatch.setattr(runner, "complete", AsyncMock(side_effect=ConnectionRefusedError("database unreachable")))

    with pytest.raises(ConnectionRefusedError):
        await process(job, "test-worker")

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by, stored.last_error) == ("running", "test-worker", None)
    adapter.send_message.assert_not_awaited()


async def test_the_worker_shutting_down_still_stops_when_the_work_turns_it_into_an_error(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock,
) -> None:
    report = await _report(db)
    step = SlowStep(10, on_cancel=RuntimeError)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report, max_attempts=1)

    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(step.started.wait(), timeout=5)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(running, timeout=5)

    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.last_error) == ("running", None)  # left for its lease to run out
    adapter.send_message.assert_not_awaited()


async def test_the_worker_shutting_down_while_the_heartbeat_winds_down_still_stops(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    quick_lease: None,
) -> None:
    report = await _report(db)
    renewing, winding_down = asyncio.Event(), asyncio.Event()

    async def renewal_slow_to_stop(*_args: Any) -> bool:
        renewing.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            winding_down.set()
            await asyncio.sleep(0.1)
            raise
        raise AssertionError("unreachable")

    async def step(*_args: Any) -> dict[str, Any]:
        await renewing.wait()  # ends while a renewal is in flight
        return {}

    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step
    monkeypatch.setattr(runner, "extend_lease", renewal_slow_to_stop)
    job = await _queued(db, report)

    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(winding_down.wait(), timeout=5)  # process() is stopping the heartbeat
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(running, timeout=5)


async def test_a_heartbeat_after_the_outcome_is_recorded_reports_no_lost_lease(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None, caplog: pytest.LogCaptureFixture,
) -> None:
    # The job is failed (no longer "running") while give_up still tells the person: a beat in
    # between finds no lease to renew, and that is not a takeover.
    report = await _report(db)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = PermanentJobError("unreadable audio")
    job = await _queued(db, report, max_attempts=1)

    async def slow_to_tell(*_args: Any) -> None:
        await asyncio.sleep(1)  # two beats of quick_lease

    monkeypatch.setattr(runner, "give_up", slow_to_tell)
    with caplog.at_level(logging.ERROR, logger="app.services.jobs.runner"):
        await process(job, "test-worker")

    assert not [r for r in caplog.records if r.getMessage().startswith("Lost the lease")]
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert stored.status == "failed"


async def test_a_slow_good_renewal_does_not_eat_into_the_retries_after_it(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None, caplog: pytest.LogCaptureFixture,
) -> None:
    # The next beat keeps its place a third of the lease after the slow renewal began, so the
    # failure that follows still has time to be retried before two thirds of the lease are gone.
    report = await _report(db)
    step = SlowStep(5)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report, max_attempts=1)
    calls = 0

    async def slow_then_unreachable(*_args: Any) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.3)  # most of a beat (0.4 s); the stored lease is the claim's 120 s
            return True
        raise ConnectionRefusedError("database unreachable")

    monkeypatch.setattr(runner, "extend_lease", slow_then_unreachable)
    with caplog.at_level(logging.WARNING, logger="app.services.jobs.runner"), pytest.raises(ConnectionRefusedError):
        await asyncio.wait_for(process(job, "test-worker"), timeout=5)

    assert [r for r in caplog.records if r.getMessage().startswith("Couldn't renew the lease")]


async def test_a_success_after_an_unnoticed_takeover_is_logged_and_left_to_the_new_owner(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The worker stalled past its lease and another took the job; the step ends well before the
    # next heartbeat would have noticed. Two runs of one report must not pass unseen.
    report = await _report(db)
    job = await _queued(db, report)

    async def taken_over_meanwhile(*_args: Any) -> dict[str, Any]:
        await _taken_by_another_worker(db, job)
        return {}

    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = taken_over_meanwhile
    with caplog.at_level(logging.ERROR, logger="app.services.jobs.runner"):
        await process(job, "test-worker")

    assert [r.getMessage() for r in caplog.records if r.name == runner.logger.name] == [
        f"Job {job.id} was taken by another worker before this one could record its success"
    ]
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by) == ("running", "other-worker")


async def test_a_job_that_keeps_its_lease_is_marked_done_and_leaves_no_task_behind(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, quick_lease: None
) -> None:
    report = await _report(db)

    async def a_few_renewals(*_args: Any) -> dict[str, Any]:
        await asyncio.sleep(1)  # two beats of quick_lease
        return {}

    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = a_few_renewals
    job = await _queued(db, report)
    tasks_before = asyncio.all_tasks()

    await process(job, "test-worker")

    assert asyncio.all_tasks() == tasks_before  # the lease keeper and the work both ended
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by) == ("done", None)


async def test_a_job_past_its_time_limit_is_stopped_and_retried(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    step = SlowStep(10)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    monkeypatch.setattr(runner.settings, "JOB_TIMEOUT_SECONDS", 0.5)
    job = await _queued(db, report)

    await asyncio.wait_for(process(job, "test-worker"), timeout=5)

    assert step.cancelled.is_set()
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.last_error) == ("queued", "TimeoutError")


async def test_the_worker_shutting_down_cancels_the_job_and_leaves_it_for_the_next_worker(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock,
    adapter: AsyncMock, quick_lease: None,
) -> None:
    report = await _report(db)
    step = SlowStep(10)
    _use_graph(monkeypatch, FakeGraph()).ainvoke.side_effect = step.run
    job = await _queued(db, report, max_attempts=1)
    tasks_before = asyncio.all_tasks()
    running = asyncio.create_task(process(job, "test-worker"))
    await asyncio.wait_for(step.started.wait(), timeout=5)

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert step.cancelled.is_set()
    assert asyncio.all_tasks() == tasks_before
    stored = await db.get(Job, job.id)
    assert stored is not None
    await db.refresh(stored)
    assert (stored.status, stored.locked_by) == ("running", "test-worker")  # its lease will run out
    await db.refresh(report)
    assert report.status == "pending"
