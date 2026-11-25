# 0012. Commit a request's writes before its response is sent

- **Status:** Accepted
- **Date:** 2026-11-25
- **Evidence:** commit `1b3a41e` ("commit a request's writes before its response is sent");
  `PROJECT_ROADMAP.md` §5, the v1.1.0 row ("writes committed before the response is sent"); the
  docstring of `get_db` in `backend/app/core/database.py`; `backend/tests/test_database_session.py`

## Context

`get_db` commits in the code after its `yield`. With FastAPI's default dependency scope, that code
runs after the response has been sent: a client could get a `201` for a row it couldn't read yet,
or for one whose commit then failed.

## Decision

Every route declares its session as `Depends(get_db, scope="function")`, so the commit runs when
the route returns, before the response. A test walks every route's dependencies and fails on any
`get_db` declared without that scope.

## Alternatives considered

- (Reconstructed.) **An explicit `await db.commit()` at the end of every route.** Easy to forget,
  and it duplicates what the dependency already does.

## Consequences

- A `2xx` means the write is durable; a failed commit becomes an error response.
- Places that must keep an outcome even if the request then fails still commit early on purpose
  (rate-limit attempts, a spent OAuth code); see
  [database sessions](../how-it-works/database-sessions.md).

## Revisit when

FastAPI changes the semantics of dependency scopes.
