"""The queue is what stops a deploy from losing reports: a job belongs to whoever holds its
lease, and when the holder dies the lease runs out and the job goes to someone else."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.jobs import queue
from app.services.jobs.queue import (
    RESUME,
    RUN,
    claim_next,
    complete,
    enqueue,
    fail_abandoned,
    fail_or_retry,
)


async def _report(db: AsyncSession, slug: str = "acme") -> Report:
    tenant = Tenant(name=slug, slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    report = Report(tenant_id=tenant.id, status="pending", requester_channel="telegram", requester_identifier="1")
    db.add(report)
    await db.commit()
    return report


async def _expire_lease(db: AsyncSession, job_id: object) -> None:
    await db.execute(update(Job).where(Job.id == job_id).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()


async def test_a_committed_job_is_claimed_by_exactly_one_worker(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN, payload={"text": "hola"})
    await db.commit()

    first = await claim_next("worker-1")
    second = await claim_next("worker-2")

    assert first is not None and first.id == job.id
    assert (first.kind, first.payload, first.attempts) == (RUN, {"text": "hola"}, 1)
    assert second is None


async def test_a_job_does_not_exist_until_its_transaction_commits(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    await enqueue(db, report_id=report.id, kind=RUN)
    await db.rollback()

    assert await claim_next("worker-1") is None
    assert (await db.execute(select(Job))).scalars().all() == []


async def test_a_delayed_job_waits_for_its_time(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    await enqueue(db, report_id=report.id, kind=RUN, delay_seconds=3600)
    await db.commit()

    assert await claim_next("worker-1") is None


async def test_a_job_whose_worker_died_goes_to_another_worker(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN)
    await db.commit()
    assert await claim_next("worker-1") is not None
    assert await claim_next("worker-2") is None  # the lease is still valid

    await _expire_lease(db, job.id)
    taken_over = await claim_next("worker-2")

    assert taken_over is not None and taken_over.id == job.id
    assert taken_over.attempts == 2


async def test_completed_jobs_are_never_claimed_again(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN)
    await db.commit()
    claimed = await claim_next("worker-1")
    assert claimed is not None

    await complete(claimed.id, "worker-1")
    await _expire_lease(db, job.id)

    assert await claim_next("worker-2") is None
    await db.refresh(job)
    assert job.status == "done"


async def test_a_failed_attempt_is_retried_later_then_abandoned(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN, max_attempts=2)
    await db.commit()

    first = await claim_next("w")
    assert first is not None
    assert await fail_or_retry(first, "w", "provider down", retryable=True) is True
    assert await claim_next("w") is None  # backing off, not hammering the provider
    await db.execute(update(Job).where(Job.id == job.id).values(run_after=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()

    second = await claim_next("w")
    assert second is not None and second.attempts == 2
    assert await fail_or_retry(second, "w", "provider still down", retryable=True) is False
    await db.refresh(job)
    assert job.status == "failed" and "still down" in (job.last_error or "")


async def test_a_permanent_failure_is_not_retried(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN)
    await db.commit()
    claimed = await claim_next("w")
    assert claimed is not None

    assert await fail_or_retry(claimed, "w", "template is gone", retryable=False) is False
    await db.refresh(job)
    assert job.status == "failed"


async def test_a_job_abandoned_on_its_last_attempt_is_reported_as_failed(
    db: AsyncSession, own_sessions: None
) -> None:
    report = await _report(db)
    job = await enqueue(db, report_id=report.id, kind=RUN, max_attempts=1)
    await db.commit()
    assert await claim_next("w") is not None
    await _expire_lease(db, job.id)

    assert await claim_next("other") is None  # no attempts left to hand out
    assert await fail_abandoned() == [(job.id, report.id)]
    assert await fail_abandoned() == []  # reported once


async def test_one_report_never_has_two_jobs_running(db: AsyncSession, own_sessions: None) -> None:
    report = await _report(db)
    await enqueue(db, report_id=report.id, kind=RUN)
    await enqueue(db, report_id=report.id, kind=RESUME)
    await db.commit()

    first = await claim_next("w1")
    assert first is not None
    assert await claim_next("w2") is None

    await complete(first.id, "w1")
    assert await claim_next("w2") is not None


def test_workers_polling_do_not_queue_behind_each_other() -> None:
    assert "FOR UPDATE SKIP LOCKED" in str(queue._CLAIM)
