# Decision records

Each record states one architectural decision: the context, what was decided, the serious
alternative and why it lost, the consequences, and what would make us revisit it.

These records were reconstructed after the fact from the dated decisions log in
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md#8-decisions-log) (§3 and §8), the commit history and
the comments in the code; each one lists the evidence it comes from. The roadmap's log stays the
running record: a new decision goes there first, and gets a record here when it shapes the
architecture.

| # | Decision | Date |
|---|---|---|
| [0001](0001-one-codebase-two-run-modes.md) | One codebase for the hosted service and self-host | 2026-10-01 |
| [0002](0002-field-app-primary-channel.md) | The field app is the primary channel; chats are optional connectors | 2026-11-06 |
| [0003](0003-postgres-job-queue.md) | A job queue in Postgres, no broker | 2026-10-01 |
| [0004](0004-langgraph-checkpointer-human-approval.md) | Human approval as a LangGraph interrupt, durable in Postgres | 2026-08-11 |
| [0005](0005-tenant-isolation-in-code.md) | Tenant isolation in code, proven by a test matrix; row-level security deferred | 2026-11-06 |
| [0006](0006-docxtpl-gotenberg-rendering.md) | Render with docxtpl and a self-hosted Gotenberg | 2026-08-10 |
| [0007](0007-structured-output-nullable-evidence.md) | Structured output, nullable fields and a quote per value | 2026-10-01 |
| [0008](0008-report-types-as-runtime-config.md) | Report types and their fields are per-company configuration | 2026-08-10 |
| [0009](0009-company-ai-keys-closed-provider-list.md) | Companies bring their own AI keys, from a closed provider list | 2026-11-17 |
| [0010](0010-mcp-server-personal-api-keys.md) | An MCP server for AI assistants, with personal API keys | 2026-11-18 |
| [0011](0011-own-oauth-authorization-server.md) | ReportAI is its own OAuth 2.1 authorization server | 2026-11-25 |
| [0012](0012-commit-before-response.md) | Commit a request's writes before its response is sent | 2026-11-25 |
| [0013](0013-settings-in-panel-encrypted.md) | Settings entered in the panel, encrypted at rest | 2026-10-01 |
| [0014](0014-published-eval-runs.md) | Paid eval runs are published, and the site may quote only them | 2026-11-25 |

## Template

```markdown
# NNNN. Title

- **Status:** Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD
- **Evidence:** roadmap entries, commits, code

## Context
## Decision
## Alternatives considered
## Consequences
## Revisit when
```
