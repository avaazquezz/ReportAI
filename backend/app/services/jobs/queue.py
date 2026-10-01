"""The job queue: one Postgres table, no broker.

A job is leased to a worker for LEASE_SECONDS and the worker keeps renewing the lease while it
runs. If the worker dies — a deploy, a crash, the machine rebooting — the lease runs out and the
next poll hands the job to someone else, which is what turns "the report is lost on every
deploy" into "the report resumes from its last checkpoint".
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.job import Job

LEASE_SECONDS = 120
# Seconds before attempt N+1 when attempt N failed: a transient provider blip usually clears.
_BACKOFF_SECONDS = (30, 120, 300)

RUN = "run"
RESUME = "resume"
DELIVER = "deliver"


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    report_id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


async def enqueue(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 3,
    delay_seconds: float = 0,
) -> Job:
    """Adds a job inside the caller's transaction — it exists if and only if the caller commits."""
    job = Job(
        report_id=report_id,
        kind=kind,
        payload=payload or {},
        max_attempts=max_attempts,
        run_after=datetime.now(UTC) + timedelta(seconds=delay_seconds),
    )
    session.add(job)
    await session.flush()
    return job


_CLAIM = text(
    """
    UPDATE jobs SET status = 'running', locked_by = :worker,
        locked_until = now() + make_interval(secs => :lease),
        attempts = attempts + 1, updated_at = now()
    WHERE id = (
        SELECT j.id FROM jobs j
        WHERE ((j.status = 'queued' AND j.run_after <= now())
            OR (j.status = 'running' AND j.locked_until < now() AND j.attempts < j.max_attempts))
          -- never two jobs of one report at once
          AND NOT EXISTS (
              SELECT 1 FROM jobs o
              WHERE o.report_id = j.report_id AND o.id <> j.id
                AND o.status = 'running' AND o.locked_until >= now())
        ORDER BY j.run_after, j.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1)
    RETURNING id, report_id, kind, payload, attempts, max_attempts
    """
)


async def claim_next(worker_id: str) -> ClaimedJob | None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(_CLAIM, {"worker": worker_id, "lease": LEASE_SECONDS})).first()
        await session.commit()
    if row is None:
        return None
    return ClaimedJob(row.id, row.report_id, row.kind, row.payload, row.attempts, row.max_attempts)


async def extend_lease(job_id: uuid.UUID, worker_id: str) -> bool:
    """False when the lease was lost (this worker was presumed dead and the job re-claimed)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.locked_by == worker_id, Job.status == "running")
            .values(locked_until=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS))
            .returning(Job.id)
        )
        renewed = result.scalar_one_or_none() is not None
        await session.commit()
        return renewed


async def complete(job_id: uuid.UUID, worker_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.locked_by == worker_id)
            .values(status="done", locked_by=None, locked_until=None)
        )
        await session.commit()


async def fail_or_retry(job: ClaimedJob, worker_id: str, error: str, *, retryable: bool) -> bool:
    """Puts the job back for another attempt, or gives up. True when it will be retried."""
    retry = retryable and job.attempts < job.max_attempts
    values: dict[str, Any] = {"last_error": error[:2000], "locked_by": None, "locked_until": None}
    if retry:
        backoff = _BACKOFF_SECONDS[min(job.attempts, len(_BACKOFF_SECONDS)) - 1]
        values |= {"status": "queued", "run_after": datetime.now(UTC) + timedelta(seconds=backoff)}
    else:
        values["status"] = "failed"
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Job).where(Job.id == job.id, Job.locked_by == worker_id).values(**values)
        )
        await session.commit()
    return retry


async def fail_abandoned() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Jobs whose worker died on their last allowed attempt: nobody will run them again.
    Returns (job_id, report_id) of each, so the caller can tell the person."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    UPDATE jobs SET status = 'failed', locked_by = NULL, locked_until = NULL,
                        last_error = 'The worker stopped before finishing and no attempts were left',
                        updated_at = now()
                    WHERE status = 'running' AND locked_until < now() AND attempts >= max_attempts
                    RETURNING id, report_id
                    """
                )
            )
        ).all()
        await session.commit()
    return [(row.id, row.report_id) for row in rows]
