# 0006. Render with docxtpl and a self-hosted Gotenberg

- **Status:** Accepted
- **Date:** 2026-08-10
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Own document rendering: docxtpl (Jinja2-tagged .docx
  templates) → self-hosted Gotenberg") and the 2026-08-10 log entry; commit `dc6503f` (rendering
  nodes, 2026-08-11)

## Context

Companies already have Word templates and want their own document, not ReportAI's. The documents
are confidential.

## Decision

The company uploads its `.docx` with Jinja2 tags; docxtpl fills it
(`backend/app/services/rendering/docx_render.py`), and Gotenberg (LibreOffice in a container on the
same server) converts it to PDF (`backend/app/services/rendering/gotenberg_client.py`).

## Alternatives considered

- **A third-party document API.** Rejected in the roadmap: an opaque dependency, and a third party
  receiving confidential documents.
- (Reconstructed.) **PDFs generated from HTML.** Companies would have to rebuild their templates,
  the friction the product exists to remove.

## Consequences

- Templates are uploaded by companies, so they're untrusted: rendering uses Jinja's
  `SandboxedEnvironment` with autoescaping, so a value like `García & Hijos` keeps the XML valid.
- A template is validated on upload against the tags it actually contains (2026-08-11 log entry),
  and a template assistant proposes tags for a document a company already fills in by hand
  (`backend/app/services/templates/assistant.py`).
- Gotenberg is one more container, with no state.

## Revisit when

A company's templates need layout LibreOffice can't reproduce faithfully.
