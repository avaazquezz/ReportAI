# Phase 1 — agent pipeline

This page described the pipeline as Phase 1 built it (August 2026). The pipeline has changed since
(a durable job queue, deliveries, the field app), and its documentation now lives in:

- [Architecture](architecture.md#one-report-end-to-end): one report end to end.
- [Report lifecycle](how-it-works/lifecycle.md): the graph, its statuses and loops, and why the
  human-approval interrupt sits before any delivery.
- [Job queue and checkpoints](how-it-works/job-queue-and-checkpoints.md): why the work runs in a
  worker fed by a Postgres queue, and how a retried run resumes from its last checkpoint.
- [ADR 0003](decisions/0003-postgres-job-queue.md) and
  [ADR 0004](decisions/0004-langgraph-checkpointer-human-approval.md): the decisions behind both.

To exercise the pipeline locally, including a simulated Telegram message and a pause that survives
a backend restart, see [local development](local-development.md).
