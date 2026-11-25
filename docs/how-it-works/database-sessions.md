# Database sessions and commit timing

When a request's writes are committed, and why every route declares its database session the same
way. Read this before you add a route or a dependency that touches the database.

## The rule

Every route that uses the database declares the session as:

```python
db: AsyncSession = Depends(get_db, scope="function")
```

`get_db` (`backend/app/core/database.py`) opens one session per request, yields it, commits when the
route returns, and rolls back and re-raises on any exception.

## Why `scope="function"`

FastAPI runs the code after a dependency's `yield` at one of two moments:

| Scope | The exit code (our commit) runs | Consequence |
|---|---|---|
| `"request"` (FastAPI's default) | After the response has been sent | A client can get `201` for a row it can't read yet, or for a row whose commit then fails |
| `"function"` | When the route function returns, before the response is sent | A `2xx` means the write is durable; a failed commit becomes an error response |

Concretely, with the default scope the field app could get `202` for a capture, immediately ask
for the report, and get a 404; or a unique violation at commit time would be logged after a
success had already reached the client. With `scope="function"`, the response is built only after
the commit succeeded. The fix landed on 2026-11-25 in commit `1b3a41e` ("commit a request's writes
before its response is sent").

`backend/tests/test_database_session.py` walks every route's dependency tree and fails if any
dependency on `get_db` is declared without `scope="function"`, so a new route can't forget it.

## Patterns you'll see

- **One request, one session.** Dependencies such as `get_current_user` take the same
  `Depends(get_db, scope="function")`, so FastAPI resolves them to the same session as the route:
  the user row and the route's writes share one transaction.
- **`flush()` inside the request, `commit()` at the end.** Routes call `await db.flush()` when they
  need generated values (an id, a server default) before returning; the commit still happens once,
  in `get_db`.
- **Explicit commits where an outcome must survive a later failure.** A few places commit early on
  purpose:
  - `AttemptLimiter.record` commits the counted attempt at once: the request usually fails right
    after, and its rollback must not take the attempt with it (`backend/app/core/rate_limit.py`).
  - `rate_limit.claim` commits to release its advisory lock.
  - `reject_report` commits the rejection before telling the sender on their channel.
  - The OAuth provider commits after spending a code or detecting refresh-token reuse, so the code
    stays spent and the revocation stays done even when the request then fails
    (`backend/app/services/oauth/provider.py`).
  - The CIMD fetch commits before contacting the publisher, so no transaction or pooled connection
    is held while a stranger's server takes its time (`backend/app/services/oauth/clients.py`).
- **Savepoints for expected conflicts.** `create_report_with_job` and `retry_report` wrap the
  insert or update that may hit a unique index in `db.begin_nested()`, so an `IntegrityError`
  rolls back only the savepoint and the rest of the transaction stays usable.

## Outside requests

The worker, graph nodes and the MCP tools don't run inside a FastAPI request. They open their own
sessions with `AsyncSessionLocal()` and commit explicitly, usually one short transaction per step
(for example `save_report` in `backend/app/services/agent/persistence.py`), so no transaction stays
open across a slow AI call. The job queue's functions each commit their own statement
(`backend/app/services/jobs/queue.py`).

The engine is shared by every session of a process: `pool_size=10`, `max_overflow=20`,
`pool_pre_ping=True`, and `expire_on_commit=False` so objects stay readable after the commit
(`backend/app/core/database.py`). The LangGraph checkpointer has its own psycopg pool (see
[job queue and checkpoints](job-queue-and-checkpoints.md#the-checkpointer)).
