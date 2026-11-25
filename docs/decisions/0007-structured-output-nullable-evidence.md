# 0007. Structured output, nullable fields and a quote per value

- **Status:** Accepted
- **Date:** 2026-10-01 (nullable fields and evidence); structured output since 2026-08-11
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Structured LLM output (structured outputs / forced
  function call), never raw JSON in a prompt") and the 2026-08-15 log entry (a required date the
  message never gave came back as `2024-01-01`); commits `4cd5d8b` (extraction and validation
  nodes, 2026-08-11) and `b76e631` ("field schema v2 with nullable extraction, more field types and
  evidence", 2026-10-01); the docstring of `backend/app/services/agent/tools/extraction_schema.py`

## Context

The report is a formal record: a plausible date nobody said is worse than a gap. The first
extraction asked the model to fill every required field, and on 2026-08-15 it invented a date
for a message that had none.

## Decision

- The model answers with **structured output** against a schema built from the document type:
  Anthropic's JSON-schema output format, or a forced function call on OpenAI-compatible APIs
  (`backend/app/services/llm.py`). Never free JSON parsed out of prose.
- **Every extractable field may be null.** "Required" means required to *send*: a required field
  left null is asked of the person over chat, or highlighted in the app, never forced out of the
  model.
- **Every value carries the shortest exact quote** that supports it, checked against what the
  person said and typed; an unmatched quote is stored as unverified.
- A validation error goes back to the model with a retry cap.

## Alternatives considered

- **JSON requested in the prompt.** Rejected in the roadmap: it brings a whole class of parsing
  failures.
- **Required fields the model must fill.** Rejected after the 2026-08-15 finding: it is how an
  invented value ends up in a formal document.
- **A forced tool call on Anthropic too.** Replaced by structured outputs: the comment in
  `_with_anthropic` records that forced tool use returns a 400 on newer Claude models.

## Consequences

- The golden-set eval grades an invented value as its own failure class and allows none
  ([Evaluations](../evals.md)).
- Approval in the app refuses while a required field is empty.
- A person's edit replaces a value and drops its quote: the quote backs what the model extracted,
  not what a person typed over it.

## Revisit when

A provider the product must support can't do structured output or forced function calls.
