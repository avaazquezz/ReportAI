# 0003. A job queue in Postgres, no broker

- **Status:** Accepted; supersedes running the graph in FastAPI `BackgroundTasks` (2026-08-11)
- **Date:** 2026-10-01
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Postgres as the job queue (`SKIP LOCKED`, lease and
  heartbeat), no Redis or Celery") and the 2026-08-11 log entry (`BackgroundTasks`, with its
  upgrade trigger); commits `792900e` (`BackgroundTasks`, 2026-08-11) and `fa3f4a9` ("durable job
  queue with leases in Postgres", 2026-10-01); revised by the 2026-11-26 log entry (lease loss)

## Context

The first pipeline ran inside the API with `BackgroundTasks`: a deploy or a crash lost whatever was
in flight, and with it the report's paid transcription and extraction. The 2026-08-11 entry named
its own trigger to move on: multiple backend instances, or durable retry of a crashed in-flight run.

## Decision

The API only records the input and a job, in one transaction. A separate worker process claims
jobs from the `jobs` table with `FOR UPDATE SKIP LOCKED`, holds a 120-second lease renewed by a
heartbeat, retries with backoff, and resumes a retried run from its last LangGraph checkpoint
([job queue and checkpoints](../how-it-works/job-queue-and-checkpoints.md)).

## Alternatives considered

- **Redis with Celery or arq.** Rejected in the roadmap: one more service to run and back up on
  every installation, and at this volume Postgres is enough. (Reconstructed: a broker also couldn't
  enqueue in the same transaction as the report row.)
- **Keep `BackgroundTasks`.** Rejected: not durable.

## Consequences

- A report and its job exist together or not at all; a resume is claimed and enqueued atomically.
- The worker polls every 2 seconds when idle, so a new report starts within about 2 seconds.
- A worker that dies delays its job by at most the lease; a job that dies on its last attempt is
  failed by the maintenance round and the person is told.
- Two jobs of one report never run at once (a clause of the claim query).
- A lapsed lease can leave two workers on one job: the one that stalled and the one that took over.
  (Revised 2026-11-26.) The old worker's heartbeat cancels its work when a renewal finds the lease
  gone, and the old worker then records nothing about the job or its report; a failure it reaches
  before noticing is dropped (`fail_or_retry` returns `"not_ours"`). The overlap lasts until its
  next heartbeat, and the checkpointer and the delivery rows keep it from producing a second
  document or email. A renewal that fails (the database unreachable) also cancels the work and
  records nothing, since whether the lease is still held is unknown; it stops the worker, whose
  container restarts, and the job is claimed again once the lease runs out (see
  [lease and heartbeat](../how-it-works/job-queue-and-checkpoints.md#lease-and-heartbeat)).

## Revisit when

Queue latency is sustained, or the workers run on several hosts (the roadmap's trigger).
