# 0008. Report types and their fields are per-company configuration

- **Status:** Accepted
- **Date:** 2026-08-10 (the initial schema already stores `document_types.field_schema`)
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Report type and field schema as per-company runtime
  config (a Pydantic model built from the database)"); `backend/alembic/versions/20260810_0001_initial_schema.py`;
  commit `cd344c8` ("keep a document type's fields in the order they were defined", 2026-10-01)

## Context

Every company has its own report types (a site safety inspection, a work order, an incident
report), each with its own fields and template. A new company or report type must not need a
release.

## Decision

A report type is a row in `document_types` with a `field_schema` (JSON), optional
`prompt_instructions` and `notification_emails`. At run time,
`build_extraction_model` and `build_result_model`
(`backend/app/services/agent/tools/extraction_schema.py`) turn the schema into Pydantic models with
`create_model`; those models are the structured-output schema and the validator.

## Alternatives considered

- (Reconstructed.) **A model class per report type in code.** Every new type would be a release
  and a deploy to every self-hosted server.

## Consequences

- The supported field types are a closed list (`FIELD_TYPES`): scalars, lists, `enum`, tables
  (`list[object]` with columns) and photo slots (`image`). Anything else is refused when the type
  is saved.
- `field_schema` is `JSON`, not `JSONB`: JSONB reorders keys, and the order fields are defined in is
  the order the bot asks, summarizes and fills photo slots in, and the panel shows them (migration
  `20261001_0014_field_schema_keeps_order.py`).
- Starter templates and the template assistant produce schemas the same way a company would.

## Revisit when

A report needs logic a schema can't express (cross-field rules, required columns in a table: the
roadmap defers the latter).
