# Glossary

The words the code, the panel and these docs use, with the name each has in the code. The panel
is in Spanish and English; the code and these docs are in English.

## The domain

| Term | Meaning |
|---|---|
| PRL | *Prevención de riesgos laborales*, occupational health and safety in Spain. The audience: safety coordinators and technicians who visit sites, inspect and must leave a written record. Also inspection and maintenance work generally. |
| Report | One filled document, from the dictation to the PDF: a row in `reports`. Its life is in [report lifecycle](how-it-works/lifecycle.md). |
| Document type (report type) | A kind of report a company makes (site visit, inspection, incident): a row in `document_types` with its field schema, prompt instructions and recipients. Configuration, not code ([ADR 0008](decisions/0008-report-types-as-runtime-config.md)). |
| Field schema | The fields of a document type, each with a type, a label, a description and whether it is required (`document_types.field_schema`). Turned into Pydantic models at run time. |
| Required field | Required to **send** the report, not a value the model must produce. Left empty, it is asked of the person or highlighted, never invented. |
| Template | The company's own `.docx` with Jinja2 tags, filled by docxtpl (`document_templates`). *Starter templates* are ready-made ones a company can start from. |
| Capture | What a technician records in the field app: a voice note and/or typed text, photos, and the chosen document type, sent to `POST /capture`. |
| Draft | A report waiting for a person's confirmation (`awaiting_approval`), or one an AI assistant started through the MCP server. |
| Evidence | The exact quote from the dictation that backs each extracted value (`reports.evidence`), marked unverified when it can't be found in what the person said. |
| Invented | In the golden-set eval, a value extracted where the message said nothing. The gate allows none. |
| Approval (confirmation) | The person's explicit go-ahead that resumes the graph to render and deliver. Over chat, a reply classified as `confirm`; in the app and the panel, the approve button. |
| Correction | Anything the person says or types to change a draft; the extraction runs again with it. |
| Delivery | One copy of a finished report sent to one destination (the origin chat, or an email address): a row in `deliveries`. |

## People and companies

| Term | Meaning |
|---|---|
| Tenant (company) | One customer organisation: a row in `tenants`. "Tenant" in the code, "company" in the panel. |
| Roles | `super_admin` (runs the hosted service), `tenant_admin`, `approver`, `viewer` and `technician`. See [authentication and sessions](how-it-works/auth-and-sessions.md#roles). |
| Instance admin | Whoever runs the installation's own settings: the company's admin on a self-hosted server, the super admin on the hosted service (`require_instance_admin`). |
| Sender | Whoever sends a message on a chat channel, known by their channel id (`requester_identifier`). *Allowed senders* is a connection's allow-list; an empty list refuses everyone. |
| Platform AI | A hosted-service company marked by the super admin (`tenants.platform_ai`) whose reports use the platform's AI keys. Every other company uses its own keys. |
| Plan | A hosted company's report quota and daily AI spend cap (`backend/app/services/plans.py`). Self-hosted servers have none. |

## Channels

| Term | Meaning |
|---|---|
| Channel, connection | A way in: `web` (the field app), `telegram`, `email` (Mailgun inbound) or `whatsapp` (experimental). A company's configured instance of one is a *channel connection* (`channel_connections`). See [channel adapters](channel-adapter.md). |
| Field app | The installable web app (PWA) technicians record with; the same Nuxt build as the panel. See [field app offline](how-it-works/field-app-offline.md). |
| Panel | The office side of the same app, under `/admin`. |

## Machinery

| Term | Meaning |
|---|---|
| Job | One unit of work for the worker: `run`, `resume` or `deliver` (`jobs`). See [job queue and checkpoints](how-it-works/job-queue-and-checkpoints.md). |
| Lease | The time a worker holds a job (120 seconds), renewed by a heartbeat; when it lapses, another worker may take the job, and the worker that lost it stops its work and records nothing about the job. |
| Graph, node | The LangGraph state machine that processes a report (`backend/app/services/agent/graph.py`) and its 25 steps. |
| Interrupt, pause | A node that stops the graph to wait for a person (`interrupt()`): which document type, missing fields, or approval. |
| Checkpoint, thread | The graph's saved state after each node, in Postgres, under `thread_id` = the report's id. |
| Execution log | One row per graph node run, with tokens, audio seconds, cost and latency (`execution_logs`). |
| Setup code | The one-time code the installer prints, required by the setup wizard on a fresh self-hosted server. |
| Magic link, sign-in code | A technician's passwordless sign-in: an emailed link valid for 15 minutes, and the same sign-in as an 8-character code to type. |

## AI assistants

| Term | Meaning |
|---|---|
| MCP | Model Context Protocol: how AI assistants call ReportAI's tools at `/mcp`. See [MCP server and OAuth](how-it-works/mcp-and-oauth.md). |
| API key | A personal key (`rpt_…`) a person makes in the panel for their assistant; it acts as them. |
| Grant (connected app) | A person's OAuth consent to one app, with the tokens it holds (`oauth_grants`). |
| CIMD | Client ID Metadata Document: an OAuth app whose `client_id` is the https URL of a document describing it, fetched by ReportAI. |
| DCR | Dynamic Client Registration (RFC 7591): an app registers itself and gets a `client_id`. |

## Evaluation and demos

| Term | Meaning |
|---|---|
| Golden set | The extraction eval: generated messages with known answers, graded field by field. See [Evaluations](evals.md). |
| Live demo | The landing's anonymous demo on the hosted service (`PUBLIC_DEMO_ENABLED`): a real report, never approved or sent, deleted after 24 hours. |
| One-click demo | A read-only demo account in the panel, enabled by `DEMO_USER_EMAIL`. |
