"""The worker's job execution: start or continue a report's run, resume a pause (by text or by
voice), and on failure either try again or give up and tell the person."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.jobs import runner
from app.services.jobs.queue import RESUME, RUN, ClaimedJob, claim_next, enqueue
from app.services.jobs.runner import PermanentJobError, execute, process


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


async def test_a_voice_reply_is_transcribed_before_the_graph_sees_it(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, checkpoints: AsyncMock, adapter: AsyncMock
) -> None:
    report = await _report(db)
    graph = _use_graph(monkeypatch, FakeGraph(paused=True))
    adapter.download_media.return_value = b"opus"
    transcribe = AsyncMock(return_value="  la fecha era el martes ")
    monkeypatch.setattr(runner.transcription, "transcribe", transcribe)

    await execute(_job(report, RESUME, {"text": None, "media_reference": "voice-9"}))

    adapter.download_media.assert_awaited_once_with("voice-9")
    assert graph.ainvoke.await_args.args[0] == Command(resume="la fecha era el martes")


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
