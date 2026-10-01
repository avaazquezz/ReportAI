# Phase 1 — agent pipeline

## Flow

```
webhook (Telegram/WhatsApp/email) → ingest_message() — deduplicated by the channel's message id
  → no report in flight for the sender → new Report row + a `run` job, in one transaction
  → a report waiting on the sender → a `resume` job carrying the reply (text, voice, or a button)
worker (python -m app.worker) → claims jobs from Postgres → runs or resumes the graph
```

Graph: `ingest → [transcribe if voice] → resolve_tenant_doctype → [ask if the type is unclear, interrupt] →
extract → validate (retry loop back to extract) → check_completeness → [ask for missing required fields, interrupt] →
human_approval_prompt → interrupt → [render if confirmed; extract again with a correction; cancel; or start a new report] →
render → convert_pdf → deliver → finalize_report`

`deliver` records one row per copy in `deliveries` (the PDF back on the channel, one email per
notification address) and sends them; a copy that fails gets a `deliver` job that retries only
the copies that did not arrive, and the panel can send any copy again.

Full node table, edges, and the reasoning behind every design decision live in
`app/services/agent/graph.py`'s module structure and were captured in the
Phase 1 plan — see the git history for `feat(backend): assemble the LangGraph
StateGraph` and surrounding commits for the detailed rationale.

## Why a human-approval interrupt exists

Per this project's `ai-agents` Claude skill: no agent sends something on a
client's behalf without an explicit human checkpoint in the graph. Sending a
filled report to a client's inbox is exactly that case. The pipeline pauses
after extraction, shows the requester a plain-language summary on the origin
channel, and waits for `CONFIRM` (proceed) or free text (treated as a
correction, routed back into extraction).

## Why a job queue in Postgres

Phase 1 ran the graph in FastAPI `BackgroundTasks`: a deploy or a crash lost
whatever was in flight. Since Fase 2 the API only records the message and a
job in the same transaction; the worker leases jobs (`FOR UPDATE SKIP LOCKED`,
renewed by a heartbeat), retries with backoff, and resumes a retried run from
its last LangGraph checkpoint instead of paying for the transcription and the
extraction again. The queue is a table in the database the app already has —
no Redis, no broker to install at a client's.

## Local verification

See `docs/local-development.md` for the full `make up / make migrate / make
seed-demo` walkthrough, including a curl-based simulation of a Telegram
message and confirmation that the interrupt/resume round trip is real and
survives a backend restart.
