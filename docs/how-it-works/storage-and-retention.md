# Storage and retention

Where ReportAI keeps files, and how long it keeps files and rows. The retention rules run in the
worker's maintenance round every 10 minutes (`maintenance` in `backend/app/worker.py`); most of them
live in `backend/app/services/data_lifecycle.py`.

## Files

Every file lives under `DOCUMENT_STORAGE_PATH` (`/app/storage` in the containers, the volume
`reportai_storage` on a self-hosted server). There is no object storage: the roadmap defers S3
until there is a second application server, since the API and the worker share the volume.

| Path under the storage folder | What | Written by |
|---|---|---|
| `inbound_tmp/<uuid>.<ext>` | A voice note uploaded from the app, or attached to an inbound email, until its job copies it | `store_voice_note` (`backend/app/services/channels/web.py`), `backend/app/api/webhooks/email.py` |
| `<report id>/audio.<ext>` | The report's voice note | `download_media_node` (`backend/app/services/agent/nodes/media.py`) |
| `<report id>/rendered.docx`, `<report id>/rendered.pdf` | The filled template and its PDF | `render_node`, `convert_pdf_node` (`backend/app/services/agent/nodes/render.py`) |
| `attachments/<tenant id>/<uuid>.jpg` | Photos, re-encoded as JPEG at most 1600 px on the longest side | `store_photo` (`backend/app/services/agent/ingestion.py`) |
| `templates/<tenant id>/` | Uploaded and starter `.docx` templates | `backend/app/services/templates/library.py` |
| `template_drafts/<tenant id>/<draft id>/` | The template assistant's work in progress | `backend/app/services/templates/assistant.py` |
| `branding/<tenant id>/` | The company's logo | `backend/app/services/branding.py` |

Photos are downsized because phone pictures are 3 to 8 MB each, and a report with six of them would
make a 40 MB Word file and email. Audio is capped at `MAX_AUDIO_BYTES` (10 MB) and photos at 15 MB
each, 10 per report, on upload (`backend/app/api/capture.py`); every photo is checked to be an image
before anything is stored, so a bad file leaves nothing behind.

Deleting files is fenced: `_ours` refuses any path that doesn't resolve inside the storage folder,
so a corrupt row can't make the worker delete something else.

## Retention rules

| What | Kept for | Setting or constant | Rule |
|---|---|---|---|
| Voice notes of reports | `AUDIO_RETENTION_DAYS` after the report was created; 0 = forever | `AUDIO_RETENTION_DAYS` (default 0; the hosted compose sets 90) | `drop_expired_audio`: deletes the file and clears `audio_path`; the transcript stays |
| Files in `inbound_tmp` | 2 days | `KEEP_INBOUND_FILES_FOR` | `drop_stale_inbound_files`. Not deleted on copy: a retried job reads it again |
| Ids of ingested chat messages | 30 days | `KEEP_INBOUND_IDS_FOR` | `prune_inbound_ids`; a channel redelivers within hours |
| A report waiting on a person | 14 days without activity, then cancelled | `PAUSED_REPORT_TTL_DAYS` | `cancel_abandoned_reports`; its checkpoints are dropped |
| Checkpoints of a terminal report | Deleted when it ends | — | See [job queue and checkpoints](job-queue-and-checkpoints.md#cleaning-up-checkpoints) |
| Template-assistant drafts | 2 days | `DRAFT_TTL` | `drop_expired_drafts` |
| Spent refresh-token ids | Until the token would have expired | — | `drop_expired_refresh_tokens` |
| Rate-limit hits | 1 day | `KEEP_HITS_FOR` | `rate_limit.prune` |
| Audit events | 365 days | `KEEP_EVENTS_FOR` (`backend/app/services/audit.py`) | `audit.prune` |
| Live-demo reports | 24 hours | `PUBLIC_DEMO_TTL` | `purge_expired_public_demo_reports`: rows, files, uploads and checkpoints |
| OAuth clients, codes, tokens, grants | See [MCP server and OAuth](mcp-and-oauth.md#revocation) | — | `prune_oauth` |
| A company that asked to be deleted | 30 days blocked, then purged | `DELETION_GRACE` | `purge_due_tenants` |

Reports themselves, their fields, PDFs and photos are kept until the company deletes them or is
deleted.

## Deleting a company

On the hosted service, a company admin asks for deletion with `DELETE /company`
(`backend/app/api/admin/company.py`), confirming with their password and the company's name. The
company is blocked at once (`is_active = false`, `deletion_requested_at` set), which ends every
session and refuses every message; reactivating it (through support) cancels the request. A
self-hosted server's only company is deleted by uninstalling, and the route answers 404 there.
After 30 days, `purge_tenant`:

1. reads every path its rows know (reports, photos, templates, logo) and its folders;
2. deletes every report's checkpoint thread;
3. deletes the files and folders;
4. deletes the `tenants` row; every company-owned table goes with it by `ON DELETE CASCADE`;
5. records a `tenant.purged` audit event, kept by the installation (the company's own audit log
   went with it).

Files and checkpoints go first because they are found through the rows: a crash halfway leaves the
rows to find them again on the next run. A company reactivated in the meantime is never purged
(the query requires it to still be blocked).

Before deleting, an admin can download everything with `GET /company/export`, limited to once an
hour (`backend/app/services/export.py`).

## Tests

`backend/tests/test_data_lifecycle.py`, `backend/tests/test_export.py`,
`backend/tests/test_capture.py`, `backend/tests/test_audio_formats.py`.
