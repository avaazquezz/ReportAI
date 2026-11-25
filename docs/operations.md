# Operations

Reference for whoever runs a ReportAI installation, self-hosted or hosted: every setting, how to
back up and restore, upgrade, monitor, and what the known failures look like. For installing a
company's own server step by step, see the [install guide](install.md); for the everyday
`reportai` commands, [maintaining an installation](maintenance.md); for a development machine,
[local development](local-development.md).

## Configuration reference

The backend reads its settings from the environment, or from a `.env` file in its working
directory, through `Settings` in `backend/app/core/config.py`; the defaults below are that file's.
`.env.example` at the repository root has every setting with a comment. A setting with no default
is required: the API and the worker refuse to start without it.

Settings marked **panel** can also be entered in the panel (the setup wizard or *Settings*); a
value saved there wins over the environment, and secrets are stored encrypted
(`backend/app/services/instance_settings.py`).

### Database and secrets

| Setting | Default | Effect |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Database host (the compose service name) |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | required | Credentials and database name; also read by the `postgres` container |
| `SECRET_KEY` | required | Signs session tokens (JWT). Rotating it signs everybody out; with `ENCRYPTION_KEY` empty, it also makes stored secrets unreadable |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime for panel users |
| `TECHNICIAN_REFRESH_DAYS` | `30` | Refresh token lifetime for technicians (renewed on each use) |
| `ENCRYPTION_KEY` | empty | Key material for secrets at rest (Fernet via HKDF); empty = derived from `SECRET_KEY`. Changing it makes every stored secret unreadable |

### Run mode and application

| Setting | Default | Effect |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` publishes `/docs`, `/redoc` and `/openapi.json`; any other value hides them. Sent to Sentry |
| `SINGLE_TENANT` | `false` | `true` = one company per installation (the installer's compose sets it) |
| `SIGNUP_ENABLED` | `false` | Self-signup at `/signup` on a free trial. Refused together with `SINGLE_TENANT=true` |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | The panel's public origin: allowed CORS origin, base of every link in emails and of the MCP PDF links, and the OAuth issuer |
| `API_ROOT_PATH` | empty | Prefix the proxy strips before the API (`/api` in every installed compose) |
| `PUBLIC_BASE_URL` | empty | Public HTTPS origin Telegram webhooks are registered under. Empty = the worker polls Telegram instead |
| `REPORTAI_VERSION` | `dev` | The release this installation runs; baked into the images, and in the self-host `.env` the image tag `reportai update` changes |
| `UPDATE_CHECK_ENABLED` | `true` | Checks GitHub for releases and security advisories (at most every 6 hours) |
| `UPDATE_REPOSITORY` | `avaazquezz/ReportAI` | Where releases and `security/advisories.json` are read from |

### AI providers (panel)

| Setting | Default | Effect |
|---|---|---|
| `EXTRACTION_PROVIDER` | `anthropic` | `anthropic` or `openai_compatible` |
| `EXTRACTION_MODEL` | `claude-sonnet-5` | Model id for extraction and reply classification |
| `ANTHROPIC_API_KEY` | empty | Key when the provider is `anthropic` |
| `EXTRACTION_EFFORT` | empty | Anthropic only: `low`, `medium` or `high`; empty = the model's default |
| `EXTRACTION_BASE_URL` | empty | Base URL for `openai_compatible` |
| `EXTRACTION_API_KEY` | empty | Key for `openai_compatible` |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout of one provider attempt (extraction and transcription) |
| `LLM_TOTAL_TIMEOUT_SECONDS` | `150` | Timeout of one extraction call across its retries |
| `TRANSCRIPTION_BASE_URL` | `https://api.groq.com/openai/v1` | Any OpenAI-compatible `/audio/transcriptions` endpoint |
| `TRANSCRIPTION_API_KEY` | empty | Its key; `GROQ_API_KEY` is the legacy name, read when this one is empty |
| `TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Transcription model |
| `TRANSCRIPTION_LANGUAGE` | `es` | Language hint when a report carries none |

On the hosted service these are the platform's settings, used only for companies marked
`platform_ai`; every other company enters its own key from a closed provider list. See
[AI providers](how-it-works/ai-providers.md).

### Pipeline, guards and timeouts

| Setting | Default | Effect |
|---|---|---|
| `DOCUMENT_STORAGE_PATH` | `storage`, relative to the working directory (`/app/storage` in the containers) | Root of every stored file |
| `GOTENBERG_URL` | `http://gotenberg:3000` | The Gotenberg service that converts `.docx` to PDF |
| `AUDIO_RETENTION_DAYS` | `0` | Days a voice note is kept; 0 = forever (the hosted compose sets 90) |
| `MAX_DOCTYPE_SELECTION_ATTEMPTS` | `3` | Times a chat sender is asked which report type |
| `MAX_VALIDATION_RETRIES` | `3` | Consecutive invalid extractions before the report fails |
| `MAX_CORRECTION_RETRIES` | `2` | Re-extractions after corrections before the limit notice |
| `NODE_TIMEOUT_SECONDS` | `240` | Ceiling for one graph node |
| `JOB_TIMEOUT_SECONDS` | `600` | Ceiling for one job |
| `PAUSED_REPORT_TTL_DAYS` | `14` | A report waiting on a person this long is cancelled |
| `SENDER_RATE_LIMIT_PER_HOUR` | `0` | New chat reports per sender per hour; 0 = off |
| `DAILY_SPEND_CAP_USD` | `0.0` | Platform-wide daily AI breaker for platform-paid calls; 0 = off. Refuses to start if `EXTRACTION_MODEL` has no price |
| `MAX_AUDIO_BYTES` | `10485760` (10 MB) | Largest voice note accepted |
| `ALLOW_ANY_SENDER` | `false` | `true` lets a chat connection with an empty allow-list accept anyone (only for a deliberately open demo) |

### Email (panel)

| Setting | Default | Effect |
|---|---|---|
| `SMTP_HOST` | empty | Outgoing mail server; without it, report emails, invitations and resets fail loudly (Telegram delivery doesn't need it) |
| `SMTP_PORT` | `587` | Port |
| `SMTP_SECURITY` | `starttls` | `starttls` (587), `ssl` (465) or `none` (a local relay only) |
| `SMTP_USER`, `SMTP_PASSWORD` | empty | Credentials |
| `SMTP_FROM_ADDRESS` | empty | Sender address |

### Channels

| Setting | Default | Effect |
|---|---|---|
| `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` | empty | WhatsApp Business Cloud API webhook (experimental); empty = disabled |
| `MAILGUN_API_KEY`, `MAILGUN_SIGNING_KEY`, `MAILGUN_INBOUND_DOMAIN` | empty | Inbound email through Mailgun; empty = disabled |

Telegram bot tokens are entered per connection in the panel and stored encrypted; they are not
settings.

### AI assistants

| Setting | Default | Effect |
|---|---|---|
| `MCP_OAUTH_ENABLED` | `false` | OAuth 2.1 sign-in for AI assistants. Needs `FRONTEND_ORIGIN` on `https` (or `http://localhost`). Off = every `/oauth/*` route is 404 and `/mcp` takes API keys only. The hosted compose sets `true` |

The MCP endpoint itself has no switch: with no API keys it is inert, and making a key is the
opt-in, person by person.

### Monitoring

| Setting | Default | Effect |
|---|---|---|
| `SENTRY_DSN` | empty | Unhandled errors and `ERROR` log lines of the API and the worker go to this Sentry project, without bot tokens or email addresses (`backend/app/core/error_tracking.py`); empty = nothing is sent |
| `WORKER_HEARTBEAT_URL` | empty | The worker requests this URL while its loop runs; must be `http(s)://`. Keep it private |
| `WORKER_HEARTBEAT_SECONDS` | `60` (at least 10) | Heartbeat period |

### Demos (hosted service only)

| Setting | Default | Effect |
|---|---|---|
| `DEMO_USER_EMAIL` | empty | Enables one-click demo sign-in (`POST /auth/demo-login`) and makes that account read-only |
| `DEMO_USER_PASSWORD`, `DEMO_TELEGRAM_BOT_TOKEN`, `DEMO_NOTIFICATION_EMAIL` | empty | Read by the demo seed script |
| `PUBLIC_DEMO_ENABLED` | `false` | The landing's live demo: an anonymous visitor dictates a visit and the real pipeline fills a report, never approved or sent, deleted after 24 hours. Refused with `SINGLE_TENANT=true` |
| `PUBLIC_DEMO_USER_EMAIL` | empty | The account whose company owns the demo's reports; must differ from `DEMO_USER_EMAIL` |
| `PUBLIC_DEMO_DOCUMENT_TYPE_ES`, `PUBLIC_DEMO_DOCUMENT_TYPE_EN` | empty | Document type ids (UUIDs) used for each language; English falls back to Spanish |
| `PUBLIC_DEMO_PER_IP_DAILY` | `3` | Tries per visitor address per 24 hours |
| `PUBLIC_DEMO_DAILY_LIMIT` | `50` | Tries for everyone per 24 hours |
| `PUBLIC_DEMO_DAILY_SPEND_USD` | `2.0` | The demo's own AI budget per UTC day; `DAILY_SPEND_CAP_USD`, when set, must be above it |

### Settings outside the backend

| Variable | Read by | Effect |
|---|---|---|
| `NUXT_PUBLIC_API_BASE` | Panel | The API's public base (`/api` behind a proxy; `http://localhost:8000` by default) |
| `NUXT_API_BASE_SERVER` | Panel | The API's internal address for server-side rendering and the OAuth discovery relay (`http://backend:8000` in the composes) |
| `NUXT_PUBLIC_SECURE_COOKIES` | Panel | `false` for an installation reached over plain HTTP, or the browser drops the session cookies |
| `NUXT_PUBLIC_LEGAL_NAME`, `_ID`, `_ADDRESS` | Panel | Who publishes the site, on the legal pages |
| `FORWARDED_ALLOW_IPS` | uvicorn | Who may set `X-Forwarded-For`; the image sets `*`, correct when only the proxy can reach the container (`backend/Dockerfile`) |
| `SITE_ADDRESS`, `HTTP_PORT`, `HTTPS_PORT`, `SECURE_COOKIES`, `COMPOSE_PROJECT_NAME`, `REPORTAI_IMAGE_PREFIX` | Self-host compose | Caddy's site address (a domain, or `:80`), the published ports, the cookie flag passed to the panel, the project name, an alternative image registry |
| `APP_DOMAIN`, `REPORTAI_TAG`, `LEGAL_*` | Hosted compose | Traefik's host rule, the image tag to run, the legal names |

### Settings that refuse to start

The validators in `Settings` stop the API and the worker at boot instead of misbehaving later:

| Combination | Why |
|---|---|
| `SIGNUP_ENABLED=true` with `SINGLE_TENANT=true` | A one-company installation has no signup |
| `WORKER_HEARTBEAT_URL` not starting with `http(s)://` | A typo would only show as an alert that never stops |
| `MCP_OAUTH_ENABLED=true` with `FRONTEND_ORIGIN` on plain HTTP (outside localhost) | Codes and tokens travel through the issuer; AI clients refuse a plain-HTTP issuer |
| `PUBLIC_DEMO_ENABLED=true` with `SINGLE_TENANT=true`, without its account and type, with the one-click demo's account, with a non-UUID type, or with `DAILY_SPEND_CAP_USD` not above the demo's budget | See the comments in `_public_demo_needs_its_company_and_type` |
| `DAILY_SPEND_CAP_USD > 0` with an unpriced `EXTRACTION_MODEL` | The cap could never trip (`require_priced_model_for_spend_cap`, checked by the API at startup) |

A refused configuration doesn't echo the values it was given (`hide_input_in_errors=True`), and
`repr()` of the settings masks every secret.

## Start order

Every compose runs the same sequence: `postgres` (and `gotenberg`) healthy → `migrate` runs
`alembic upgrade head && python scripts/setup_checkpointer.py` and exits → `backend` and `worker`
start. The worker refuses to start if the LangGraph checkpoint tables are missing.

## Backups and restore

`reportai update` dumps the database before updating, but that dump is a way back from a bad
update, kept on the same disk: it is not a backup. Back up three things, off the server:

1. **The database.** On a self-hosted server, from the installation folder:

   ```sh
   docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > reportai-db.sql.gz
   ```

   This is the command `reportai update` itself runs (`infra/install/reportai`).

2. **The storage volume** (`reportai_storage` on a self-hosted server): templates, photos, audio and
   PDFs. Nothing else can regenerate an uploaded template.
3. **The `.env` file**, kept apart from the dumps. Without its `ENCRYPTION_KEY` (or `SECRET_KEY`, if
   that is empty), the stored AI keys, mail password and bot tokens can't be read and have to be
   entered again.

`infra/backup.sh` does the first two for the hosted compose's container and volume names, and
takes `PG_CONTAINER` and `STORAGE_VOLUME` to point it at others. It writes under a `.partial` name,
verifies the gzip and the dump's completion footer before keeping a file, prunes local copies
older than `KEEP_DAYS` (14), runs `BACKUP_SYNC_CMD` to push the folder off the server, and pings
`BACKUP_PING_URL` on success so a dead-man's-switch monitor alerts when a night is missed.

`infra/restore.sh --yes DB_BACKUP [STORAGE_BACKUP]` drops and recreates the database and
overwrites the storage volume's files; stop the API first and start it again afterwards. To
rehearse without touching the live database, set `TARGET_DB` to another database name. Rehearse a
restore before you need one, on a scratch server, and check that a report downloads afterwards.

> **Warning:** restoring is destructive: it replaces the live database and files.

## Upgrades

On a self-hosted server, `reportai update [X.Y.Z]` dumps the database to the installation's
`backups/` folder, sets `REPORTAI_VERSION` in `.env`, pulls the images, runs the migrations and
restarts, then waits for `/health`. If the new version doesn't start, it prints how to go back:
the previous `REPORTAI_VERSION`, the dump, `reportai restart`. Going back a version needs `--force`,
because migrations are not undone. See [maintaining an installation](maintenance.md) for release
notices and security advisories.

On the hosted compose, `make deploy` pulls the images tagged `REPORTAI_TAG`, runs `migrate` and
restarts the services.

Upgrades keep a self-hosted server's behaviour: new feature flags default to off and new columns
get neutral defaults (see [Architecture, invariants](architecture.md#self-host-must-not-change)).

## Health and monitoring

| Check | What it tells | How |
|---|---|---|
| `GET /api/health` (`/health` on the API itself) | The API answers and reaches the database | `200 {"status":"ok","database":"ok","version":...}`, or `503` when the database is down (`backend/app/api/health.py`). Monitor it from **outside** the server |
| Worker heartbeat | The worker's loop is turning | Set `WORKER_HEARTBEAT_URL` to a push monitor (healthchecks.io, Uptime Kuma) with a period of `WORKER_HEARTBEAT_SECONDS` and a few minutes' grace. The worker stops pinging when its loop hasn't moved for longer than `JOB_TIMEOUT_SECONDS` plus 5 minutes |
| Container health | Docker's own view | `docker compose ps`. The backend image's health check requests `/`, which doesn't touch the database; the worker's is disabled |

The API can't see the worker: with the worker stuck, the panel still answers while reports wait.
That is why the heartbeat exists.

### Logs

The API and the worker log one JSON object per line (`backend/app/core/logging.py`). Every line
emitted while a job runs carries `report_id`, `tenant_id` and `job`, so you can follow one report:

```sh
reportai logs worker | grep '"report_id": "REPORT_ID"'
```

Replace `REPORT_ID` with the id from the panel's report page. On the hosted compose, use
`docker logs` on the backend or worker container.

The `execution_logs` table holds one row per graph node run, with its status, latency, model,
tokens and cost; the panel's usage page reads it.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| API or worker exits at boot: "LangGraph checkpoint tables are missing" | `migrate` didn't run | Run the migrate step (`reportai restart` runs it; in development `make migrate`) |
| A report fails with "A stored secret can't be decrypted" | `ENCRYPTION_KEY` (or `SECRET_KEY` with no `ENCRYPTION_KEY`) changed since the secret was saved | Enter the AI keys, mail password and bot tokens again in the panel |
| New reports refused with the `not_configured` message | No AI provider configured for this company (or, for voice, no transcription) | Enter it in the panel; on the hosted service each company enters its own |
| Reports fail with the `ai_key_rejected` message | The provider answered 401 or 403 | Enter a working key; then *Retry* the failed report in the panel |
| A chat sender gets a message with their id and nothing happens | The connection's allow-list doesn't include them (an empty list refuses everyone) | Add the id shown in the message, or invite the person from *Channels* |
| Reports stay `pending` | The worker is down or stuck | Check the worker's logs and heartbeat; a job whose worker died is picked up again once its lease (120 s) expires |
| A report ends `cancelled` without anyone cancelling it | Nobody answered for `PAUSED_REPORT_TTL_DAYS` | Expected |
| Reports end `delivery_failed` | Every copy failed (often SMTP not set up) | Set up email, then resend from the report's page |
| Nobody can sign in on an installation reached by IP | Session cookies are `Secure` and the panel is on plain HTTP | Set `SECURE_COOKIES=false` (self-host) or `NUXT_PUBLIC_SECURE_COOKIES=false`, and restart; better, give it a domain |
| The field app can't record or install | It is served over plain HTTP | Give the installation a domain (HTTPS) |
| The API logs "This installation is not set up yet" | A fresh self-hosted server with no users | `reportai setup-code`, then open the panel's `/setup` |
| `/.well-known/oauth-authorization-server` answers 500 | The panel can't reach the API to relay the document | Set `NUXT_API_BASE_SERVER` |
| It answers 404 | `MCP_OAUTH_ENABLED` is off | Expected on a self-hosted server; assistants use API keys |
| A Telegram bot stays silent with a domain configured | The webhook wasn't registered (`PUBLIC_BASE_URL` empty or not public HTTPS) | Set `PUBLIC_BASE_URL` and restart: the worker registers every bot's webhook at start |
