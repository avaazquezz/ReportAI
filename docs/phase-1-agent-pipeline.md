# Phase 1 — agent pipeline

## Flow

```
webhook (Telegram/WhatsApp/email) → start_or_resume_pipeline()
  → new sender+tenant with no pending report → new Report row, background task runs the graph from START
  → sender+tenant already awaiting a reply → background task resumes the same graph via Command(resume=...)
```

Graph: `ingest → [transcribe if voice] → resolve_tenant_doctype → [ask if >1 doc type, interrupt] →
extract → validate (retry loop back to extract) → human_approval_prompt → interrupt →
[render pipeline if confirmed, or back to extract with the correction if not] →
render → convert_pdf → deliver_email → deliver_channel_reply → finalize_report`

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

## Why BackgroundTasks, not a job queue

The human-approval pause means the graph must survive across two separate
HTTP requests regardless of which task runner kicks off execution — that
durability comes from LangGraph's Postgres checkpointer, not from
`BackgroundTasks` itself. `BackgroundTasks` avoids new infra (no Redis, no
worker process) at Phase 1's scale. Move to `arq` + Redis when either the
backend runs more than one instance, or a crashed in-flight run needs
automatic retry without the requester re-sending their message.

## Local verification

See `docs/local-development.md` for the full `make up / make migrate / make
seed-demo` walkthrough, including a curl-based simulation of a Telegram
message and confirmation that the interrupt/resume round trip is real and
survives a backend restart.
