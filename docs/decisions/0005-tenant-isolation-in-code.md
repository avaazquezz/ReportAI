# 0005. Tenant isolation in code, proven by a test matrix; row-level security deferred

- **Status:** Accepted
- **Date:** 2026-08-11 (scoping in code); 2026-11-06 (the matrix)
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Tenant isolation enforced in code (`core/scoping.py`) and
  proven by a test matrix; Postgres RLS deferred"), §6, and the 2026-08-11 log entry ("every
  tenant-scoped endpoint resolves `tenant_id` from the authenticated user … cross-tenant access
  renders as 404"); commit `57d120a` ("prove no route lets one company reach another's data")

## Context

Several companies share one database on the hosted service. One company reaching another's reports
would be the worst failure the product can have.

## Decision

Isolation is enforced in the application, in one place, and proven by tests:

- The company always comes from the authenticated user (`require_tenant_id`), never from the
  request body or query.
- Rows are loaded by id with `get_scoped_or_404` (`backend/app/core/scoping.py`): another company's
  row is a 404, never a 403, because a 403 confirms the id exists.
- `backend/tests/test_tenant_isolation.py` calls every route with an id as another company's users
  and fails when a new route with an id isn't classified in it.

## Alternatives considered

- **Postgres row-level security now.** Deferred (roadmap §3 and §6): it comes with the first
  enterprise client or an audit that asks for it. The log does not record a cost comparison.

## Consequences

- Every new route with a path id joins the matrix in the same change.
- Helpers that return "a row this person may see" (`visible_report`, `revocable_key`,
  `revocable_grant`) keep the 404 rule for finer rules too, such as a technician and a colleague's
  report.
- The MCP server reuses the panel's helpers, so the same rules hold for AI assistants; its eval
  checks that another company's data never reaches a tool result.

## Revisit when

The first enterprise client, or an audit, asks for row-level security.
