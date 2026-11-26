# Job queue and checkpoints

How a report's work survives deploys, crashes and retries. Read this before you change
`backend/app/services/jobs/`, `backend/app/worker.py` or anything that enqueues a job.

Two mechanisms work together, and it helps to keep them apart:

- The **job queue** decides *who* works on a report and *when*: a row in `jobs`, leased to one
  worker at a time.
- The **LangGraph checkpointer** remembers *where* the report's graph got to: after every node, its
  state is written to Postgres under `thread_id = report id`.

A job is a ticket at a counter; the checkpoint is the half-filled form clipped to it. If the clerk
leaves mid-way, the next clerk takes the ticket and carries on from the form, instead of asking the
customer to start over (and paying again for the transcription and the extraction).

## The queue

A job is one row in `jobs` (`backend/app/models/job.py`):

| Column | Meaning |
|---|---|
| `kind` | `run` (start a report), `resume` (answer a pause), `deliver` (send copies that failed) |
| `payload` | What the job needs: the text and media reference, the reply, the document type chosen in the app |
| `status` | `queued`, `running`, `done`, `failed` |
| `attempts`, `max_attempts` | Attempts so far; 3 by default |
| `run_after` | Not claimed before this time (backoff, delayed delivery retries) |
| `locked_by`, `locked_until` | The worker holding the lease, and until when |
| `last_error` | The last failure, cut to 2000 characters |

### Enqueue in the caller's transaction

`enqueue` (`backend/app/services/jobs/queue.py`) only adds and flushes the row: the job exists if
and only if the caller commits. Every producer relies on this:

- `create_report_with_job` (`backend/app/services/agent/ingestion.py`) inserts the report and its
  `run` job together, so a report can never exist without something that will process it.
- `request_resume` flips a paused report to `pending` with a conditional `UPDATE`
  (`ReportRepository.claim_for_resume`) and enqueues the `resume` job in the same transaction. Of
  two duplicate replies, or two reviewers clicking at once, only one wins the `UPDATE`; the other
  enqueues nothing.
- `request_resend` and the `deliver` node enqueue `deliver` jobs next to the delivery rows they
  reset (`backend/app/services/delivery/deliveries.py`).

### Claim

`claim_next` runs one statement (`_CLAIM` in `queue.py`):

```sql
UPDATE jobs SET status = 'running', locked_by = :worker,
    locked_until = now() + make_interval(secs => :lease),
    attempts = attempts + 1, updated_at = now()
WHERE id = (
    SELECT j.id FROM jobs j
    WHERE ((j.status = 'queued' AND j.run_after <= now())
        OR (j.status = 'running' AND j.locked_until < now() AND j.attempts < j.max_attempts))
      AND NOT EXISTS (
          SELECT 1 FROM jobs o
          WHERE o.report_id = j.report_id AND o.id <> j.id
            AND o.status = 'running' AND o.locked_until >= now())
    ORDER BY j.run_after, j.created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1)
RETURNING id, report_id, kind, payload, attempts, max_attempts
```

What each part guarantees:

- `FOR UPDATE SKIP LOCKED` lets several workers poll at once without blocking each other or taking
  the same row.
- A `running` job whose lease expired is claimable again: that is how a dead worker's job is
  recovered, with no coordinator.
- `NOT EXISTS` keeps two jobs of one report from running at once (a `resume` waits for the `run`
  that is still delivering, for example), so the graph's thread is never advanced by two workers.
- `attempts` is counted at claim time, so a worker that dies mid-job still uses up an attempt.

### Lease and heartbeat

The lease lasts `LEASE_SECONDS` (120, `backend/app/services/jobs/queue.py:20`). `process`
(`backend/app/services/jobs/runner.py:231`) runs `execute` as a task of its own and starts
`_heartbeat` (`runner.py:204`) next to it, which calls `extend_lease` every 40 seconds
(`LEASE_SECONDS / 3`). `extend_lease` (`queue.py:96`) only renews a row still `running` and still
`locked_by` this worker. With the lease at three times the renewal interval, it lapses only when a
worker goes 120 seconds without renewing: it died, or it stalled.

A lapsed lease makes the job claimable again (see [Claim](#claim)), so a worker that stalled and
then recovered shares the report with the worker that took the job over. The rule is that **once
a worker has lost the lease, the job and its report are the new owner's, and the old worker
records nothing about either**. The following paths enforce it:

| When the old worker… | It… | Code |
|---|---|---|
| …finds the lease gone at its next heartbeat (`extend_lease` returns false) | Logs an error, sets the `lease_lost` event `process` passed it, and cancels the work in hand. `process` checks that event, so it returns without calling `complete`, `fail_or_retry` or `give_up`, also when a library turns the cancellation into an error of its own. | `_heartbeat` and `process` (`runner.py:204-269`) |
| …sees the work fail before its heartbeat noticed the takeover | Calls `fail_or_retry`, which updates only a row still `locked_by` this worker and, finding none, returns `"not_ours"`. `process` logs an error and skips `give_up`, so the report is not failed under its new owner. | `fail_or_retry` and `FailOutcome` (`queue.py:30`, `queue.py:120-137`); `runner.py:259-264` |
| …sees the work succeed before its heartbeat noticed the takeover | Calls `complete`, which also filters on `locked_by` and so changes nothing. | `complete` (`queue.py:110`) |

On a last attempt nobody claims the job again (the claim requires `attempts < max_attempts`); the
maintenance round fails it with `fail_abandoned`, which clears `locked_by`, so a late
`fail_or_retry` returns `"not_ours"` there too (see [Retry or give up](#retry-or-give-up)).

> **Note:** the old worker stops at its next heartbeat, not the moment its lease lapses, and the
> cancellation lands at the work's next `await`. Until then both workers may run graph nodes for
> the same report. The checkpointer and the delivery rows (one per copy, skipped once `sent`) keep
> that overlap from producing a second document or email.

If a renewal itself fails (`extend_lease` raises, for example because the database is
unreachable), nobody knows whether this worker still holds the lease. `_heartbeat` cancels the work
at once and re-raises, and `process` re-raises that error instead of recording anything, also when
the work turned the cancellation into an error of its own (`_renewal_error` and `process`,
`runner.py:221-253`). The job stays `running` and `locked_by` this worker, and the report keeps its
status. The error leaves the worker's loop and ends the process (`main`, `backend/app/worker.py`),
and Docker restarts the container (`restart: always` in `infra/docker-compose.prod.yml`,
`unless-stopped` in `infra/install/docker-compose.yml` and `infra/docker-compose.yml`). Once the
lease runs out, a worker claims the job again and a retried run carries on from its last
checkpoint; on a last attempt the maintenance round fails it instead. A renewal that fails after
the work has ended, while `process` records the outcome, still stops the worker: `process` awaits
the heartbeat last and so re-raises its error (`runner.py:265-269`). This is deliberate: a worker
that can't reach its database fails loud instead of carrying on.

The worker's `id` is `<hostname>-<pid>` (`backend/app/worker.py`, `main`).

### Timeouts

Three ceilings keep one stuck call from holding a worker:

| Ceiling | Setting | Default | Where |
|---|---|---|---|
| One provider call (per attempt) | `LLM_TIMEOUT_SECONDS` | 60 s | `backend/app/services/llm.py`, `backend/app/services/transcription.py` |
| One provider call, all its attempts | `LLM_TOTAL_TIMEOUT_SECONDS` | 150 s | `structured_completion` |
| One graph node | `NODE_TIMEOUT_SECONDS` | 240 s | `observed_node` in `backend/app/services/observability/execution_log.py` |
| One job | `JOB_TIMEOUT_SECONDS` | 600 s | `process` in `runner.py` |

### Retry or give up

`process` turns a job's failure into a retry or a surrender instead of raising. It raises on
purpose only to stop the worker, in two cases: a cancellation of its own task (the work is
cancelled with it and the job stays `running` until its lease runs out), and a lease it can't
renew (see [Lease and heartbeat](#lease-and-heartbeat)). A database error while it records the outcome also
escapes. When `execute` fails, or runs past
`JOB_TIMEOUT_SECONDS`, and the worker still holds the lease:

1. `fail_or_retry` puts the job back as `queued` with a backoff when the error is retryable and
   attempts are left, and returns `"retrying"`. The backoff after attempt 1 is 30 s, after
   attempt 2 is 120 s, and 300 s after that (`_BACKOFF_SECONDS`).
2. A `PermanentJobError` (`backend/app/services/jobs/errors.py`) is never retried: no attempt can
   fix it. Its subclasses carry the message the person gets: `NotConfiguredError` (no AI key or
   transcription provider set) and `ProviderRejectedKeyError` (the provider answered 401 or 403),
   both in `backend/app/services/instance_settings.py`.
3. With no retry left, `fail_or_retry` marks the job `failed` and returns `"failed"`, and
   `give_up` marks the report `failed` (only if it is not already terminal:
   `mark_report_failed` in `backend/app/services/agent/nodes/deliver.py`), tells the sender in
   their company's language, and deletes the report's checkpoints.

A job whose worker died on its **last** attempt is never claimed again (the claim requires
`attempts < max_attempts`). The worker's maintenance round finds it with `fail_abandoned`, marks it
`failed`, and calls `give_up` with the `interrupted` message.

## The checkpointer

`backend/app/core/langgraph_checkpointer.py` sets up `AsyncPostgresSaver` from
`langgraph-checkpoint-postgres`:

- **Its own driver and pool.** The checkpointer needs psycopg; the app uses asyncpg through
  SQLAlchemy. Both point at the same database. The pool (`max_size=10`, autocommit) checks each
  connection before handing it out, so connections that died while idle (Postgres restarted) are
  not reused.
- **Only the worker opens it.** The API never reads or writes checkpoints: the nodes copy what the
  panel needs onto the report row (`save_report`, `backend/app/services/agent/persistence.py`).
- **Tables are created by `migrate`**, never at startup: `setup()` uses `CREATE INDEX
  CONCURRENTLY` with no lock of its own and races when two processes run it on a fresh database.
  `init_checkpointer` refuses to start when the `checkpoint_migrations` table is missing, so a
  forgotten migration is an error at boot instead of a failed first report.
- **A restricted deserializer.** `CHECKPOINT_SERDE` lists the only classes a checkpoint may bring
  back (`AgentState`, `DocumentTypeOption`, `ToolUsage` and asyncpg's UUID). Add any new class that
  travels in the graph state to that list, or paused reports can't resume.

### Run, resume, retry

`execute` dispatches on the job's kind (`runner.py`):

- **`run`, first attempt.** Builds a fresh `AgentState` from the report and the job's payload and
  calls `graph.ainvoke(state, config)` with `thread_id = str(report.id)`.
- **`run`, a later attempt.** If the thread already has a checkpoint (`snapshot.values`), it calls
  `ainvoke(None, config)`, which continues from the last completed node. If the snapshot has no
  next node, the earlier attempt actually finished and nothing runs.
- **`resume`.** If no task of the snapshot is waiting on an interrupt, an earlier attempt already
  delivered this answer and the job does nothing. Otherwise it turns a voice reply into text first
  (logged as `transcribe_reply`, since no node runs it) and calls
  `ainvoke(Command(resume=reply), config)`.
- **`deliver`.** Runs `send_pending` outside the graph: it sends only the copies not yet `sent`
  and raises `DeliveryFailed` (retryable) when some still fail.

When `ainvoke` returns with `__interrupt__`, the checkpoint is already saved;
`_mark_paused_if_interrupted` reads the interrupt's `kind` and sets the report's status:

| Interrupt `kind` | Node | Report status |
|---|---|---|
| `select_document_type` | `await_document_type_reply` | `awaiting_doctype_selection` |
| `missing_fields` | `await_missing_fields` | `awaiting_details` |
| `confirm_report` | `await_human_approval` | `awaiting_approval` |

Every node is wrapped by `observed_node`, which writes one `execution_logs` row per run with status
`success`, `interrupted` or `error`. `interrupt()` works by raising `GraphInterrupt` through the
node, so the wrapper logs it as `interrupted` and re-raises it instead of recording an error.

### Cleaning up checkpoints

A checkpoint thread is about 250 KB, and a finished report never resumes. Three places delete
threads:

1. After any job, `_forget_finished_thread` deletes the thread if the report is terminal.
2. `give_up` deletes it when a report fails.
3. The maintenance round's `drop_finished_checkpoints` (`backend/app/worker.py`) is the safety net
   for rejections, cancellations and crashes: it joins `reports` with `checkpoints` and deletes
   the threads of every terminal report.

## The worker loop

`main` in `backend/app/worker.py`:

1. Opens the checkpointer, installs SIGTERM and SIGINT handlers, and starts either the Telegram
   pollers (no `PUBLIC_BASE_URL`) or a one-off registration of every bot's webhook.
2. Starts the optional heartbeat to `WORKER_HEARTBEAT_URL` (see [Operations](../operations.md#monitoring)).
3. Loops until stopped: runs `maintenance` when 10 minutes have passed since the last round, claims
   one job, processes it, or waits up to 2 seconds when there is none.

On SIGTERM it stops taking jobs and finishes the one in hand. The compose files give the worker a
`stop_grace_period` of 5 minutes, shorter than `JOB_TIMEOUT_SECONDS`; a job still running when
Docker kills the container is recovered by the next worker once its lease expires.

`maintenance` runs, in order: fail abandoned jobs; cancel reports waiting on a person for more than
`PAUSED_REPORT_TTL_DAYS` (14) and drop their checkpoints; drop finished checkpoints; prune spent
refresh-token ids, rate-limit hits and audit events; roll plan periods; drop template-assistant
drafts; purge companies past their deletion grace; purge live-demo reports; apply audio retention
and sweep temporary files; prune OAuth clients, codes and revoked grants. A failure in maintenance
is logged and the loop carries on.

## Limits and when to revisit

- One worker process handles one job at a time. Throughput scales by running more workers; the
  claim query already supports that.
- The queue polls every 2 seconds when idle: a new report starts within about 2 seconds, with no
  `LISTEN/NOTIFY`.
- The trigger to move off Postgres ([ADR 0003](../decisions/0003-postgres-job-queue.md)) is
  sustained queue latency or several worker hosts.

## Tests

- `backend/tests/test_job_queue.py`: claiming, leases, the one-job-per-report rule, backoff, a
  worker whose job was taken over unable to fail it.
- `backend/tests/test_job_runner.py`: retry, permanent errors, giving up, resuming from a
  checkpoint; a lost lease cancelling the work and recording nothing, a renewal that fails
  stopping the work and the worker, a failure after an unnoticed takeover, the job timeout, and the
  worker's own cancellation, also after a lost lease.
- `backend/tests/test_interrupt_resume.py`: a pause and resume against the real checkpointer.
- `backend/tests/test_langgraph_checkpointer.py`, `backend/tests/test_pause_status.py`.
