# 0004. Human approval as a LangGraph interrupt, durable in Postgres

- **Status:** Accepted
- **Date:** 2026-08-11; the resume path fixed on 2026-08-15
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Human confirmation before anything is sent … a LangGraph
  interrupt that the sender or the panel resumes") and the log entries of 2026-08-11 ("LangGraph's
  Postgres checkpointer is the durability mechanism for the human-approval pause/resume, not the
  task runner") and 2026-08-15 (resume through `claim_for_resume`); commits `dd27bbc`
  (checkpointer) and `c7e25d3` (approval interrupt)

## Context

A report is a formal record sent on a company's behalf. Nothing may be sent without a person
confirming it, and the confirmation may come minutes or days later, across deploys.

## Decision

The approval is an edge of the graph, not a check in the interface: `await_human_approval` calls
LangGraph's `interrupt()`, and the `AsyncPostgresSaver` checkpointer stores the graph's state under
`thread_id = report id`. Asking which report type and asking for missing fields are interrupts of
the same kind. The checkpointer holds the paused state; the job queue
([0003](0003-postgres-job-queue.md)) decides who resumes it.

## Alternatives considered

- (Reconstructed.) **A status on the report, and a fresh pipeline run on confirmation.** The
  2026-08-15 entry describes exactly this failure while the resume branch was dead code: a CONFIRM
  reply started a new run with a new extraction and orphaned the paused one. It repeats paid work,
  and the graph's question and correction loops would have to be rebuilt outside it.
- (Reconstructed.) **Paused graphs in memory.** A deploy would lose every pending approval.

## Consequences

- A pause survives restarts; `backend/tests/test_interrupt_resume.py` proves it against the real
  checkpointer.
- The report's status mirrors the pause (`awaiting_*`), set when `ainvoke` returns with
  `__interrupt__`; resumes go through an atomic `claim_for_resume`, so a duplicate reply can't
  resume a thread twice.
- The nodes copy what the panel shows onto the report row: the API never reads checkpoints.
- Checkpoints cost about 250 KB per report, so they are deleted when a report ends, and paused
  reports are cancelled after `PAUSED_REPORT_TTL_DAYS`.
- Every class that travels in the state must be on the checkpoint deserializer's allowlist
  (`CHECKPOINT_SERDE`).

## Revisit when

LangGraph's checkpoint format or its Postgres saver changes in a way that breaks paused threads.
