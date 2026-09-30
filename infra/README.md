# Infra

- `docker-compose.yml` — local development (hot reload, Postgres port exposed, source bind-mounted). Run via the root `Makefile`.
- `docker-compose.prod.yml` — private-server deployment behind Traefik. Assumes an external `web` Docker network and a Traefik certificate resolver named `le` already exist on the server. Single-domain routing: `${APP_DOMAIN}/api/*` → backend (StripPrefix + `API_ROOT_PATH=/api`), everything else → the Nuxt frontend.

## Production deploy runbook

Prerequisites on the server: Docker + Compose, the shared Traefik already running
on the external `web` network with a certificate resolver named `le`.

### 1. Domain — `reportai.vazquezlabs.com`

`reportai.is-a.dev` was the original plan (see the 2026-08-13 decisions-log
entry) but is-a.dev's Terms of Service rule it out on multiple counts:
commercial/for-profit use is explicitly prohibited (§4.8), AI-agent products
are called out by name as disallowed (§4.15), and PRs authored by an AI
coding tool are explicitly rejected on sight (§5) — see the 2026-08-16
decisions-log entry. `vazquezlabs.com` is an owned, currently-unused domain
earmarked as the umbrella brand for presenting all of this developer's
projects — a subdomain per project (`reportai.vazquezlabs.com` here) reads
as a more deliberate portfolio structure than piggybacking on the personal
consulting domain, and it sidesteps every is-a.dev restriction with no
external review. Add an `A` record for `reportai` → the server's IP through
whatever DNS host manages `vazquezlabs.com`.

### 2. Server checkout + environment

```bash
cd /home/vazquezdev/proyectos   # convention this server already uses for every other project
git clone https://github.com/avaazquezz/ReportAI.git && cd ReportAI
cp .env.example .env   # then fill EVERY value with real production secrets
```

Production-specific values (see the commented blocks at the bottom of
`.env.example`): `APP_DOMAIN`, `API_ROOT_PATH=/api`, `FRONTEND_ORIGIN`,
`PUBLIC_BASE_URL`, `ENVIRONMENT=production` (this is also what closes `/docs` and
`/openapi.json`), `LEGAL_NAME` / `LEGAL_ID` / `LEGAL_ADDRESS` (published on
`/aviso-legal`), the `DEMO_*` trio, and the guards (`SENDER_RATE_LIMIT_PER_HOUR`,
`DAILY_SPEND_CAP_USD`). Generate `SECRET_KEY` and `DEMO_USER_PASSWORD` fresh — never
reuse dev values. `.env` lives only on the server; it is never committed.

The AI provider is chosen here, per installation: `EXTRACTION_PROVIDER` (`anthropic` or
`openai_compatible` + `EXTRACTION_BASE_URL` / `EXTRACTION_API_KEY`), `EXTRACTION_MODEL`, and
the independent `TRANSCRIPTION_*` settings — with the client's own keys. SMTP, WhatsApp and
Mailgun are optional: leave them unset to disable those features.

A channel with an empty `allowed_senders` list rejects every message (unless
`ALLOW_ANY_SENDER=true`), so after connecting a Telegram bot, add the administrator's
Telegram id to it in the panel. The rejected id is written to the backend log, so it can be
copied from there (`docker logs reportai_backend | grep "Rejected message"`).

### 3. Bring the stack up

CI publishes the backend and frontend images to GHCR on every push to `main`
(`.github/workflows/publish.yml`), tagged with the commit SHA and `latest`. The server pulls
them instead of building; pin a release with `REPORTAI_TAG=<sha or v-tag>` in `.env`.

```bash
make deploy    # pull images → run the one-shot `migrate` job → restart
```

`migrate` applies the Alembic migrations **and** LangGraph's checkpoint tables
(`scripts/setup_checkpointer.py`), and the API only starts after it completes
successfully. The API refuses to start if the checkpoint tables are missing, so a forgotten
migration shows up as a clear error instead of failing the first report.

If the GHCR packages are private, `docker login ghcr.io` first; to build on the server
instead, use `docker compose --project-directory . -f infra/docker-compose.prod.yml up -d --build`.

Deliberately **not** run here: `scripts/seed_demo_tenant.py` and
`scripts/set_telegram_webhook.py`. The public interactive demo (Telegram bot
+ demo-login tenant) stays dormant until a real paying client needs it — see
the 2026-08-16 decisions-log entry. The landing page's own pre-generated
static demo (`frontend/public/demo/`) needs neither. Seeding without
`DEMO_USER_EMAIL`/`DEMO_USER_PASSWORD` set would also create a full-write
account under a publicly-known default password (`seed_demo_tenant.py`'s
fallback), reachable through the normal login form — a real gap, not just an
unwanted feature. To activate the demo later: set `DEMO_USER_EMAIL`,
`DEMO_USER_PASSWORD`, `DEMO_TELEGRAM_BOT_TOKEN`, `DEMO_NOTIFICATION_EMAIL`,
restart, then run both scripts above.

### 4. Smoke test (the real thing, not curl)

`curl https://reportai.vazquezlabs.com/api/health` returns 200, and the
landing page loads with its static demo audio/PDF playing and the language
auto-detecting/toggling correctly. No Telegram round-trip test — the bot
stays off (see above).

### 5. Backups (host crontab)

```cron
30 4 * * * BACKUP_SYNC_CMD='rclone sync /var/backups/reportai remote:reportai-backups' BACKUP_PING_URL='https://hc-ping.com/<uuid>' /path/to/ReportAI/infra/backup.sh >> /var/log/reportai-backup.log 2>&1
```

`infra/backup.sh` dumps the database and archives the storage volume (customers' `.docx`
templates and PDFs live there, and nothing else can regenerate them). It verifies both
files before keeping them, exits non-zero on any failure (so cron/monitoring see it), and
prunes local copies older than `KEEP_DAYS` (14).

Two things make it a real backup rather than a copy on the same disk:

- `BACKUP_SYNC_CMD` runs after a successful backup — use it to push `BACKUP_DIR` off the
  server, encrypted (e.g. `rclone` with a `crypt` remote, or `restic`). The dumps contain
  client data.
- `BACKUP_PING_URL` is pinged on success; a dead-man's-switch monitor (e.g. Healthchecks.io)
  alerts you when a night *doesn't* report in, which a failing script alone can't tell you.

**Rehearse the restore** before you need it, on a scratch server: stop the API, run
`infra/restore.sh --yes <db-backup> [<storage-backup>]`, start the API, and check that a
report downloads. The script drops and recreates the database.

No demo-reset cron line — there is no demo tenant to reset while the public demo stays dormant.

### 6. Monitoring (minimal, deliberate)

- Container health: every service defines a Docker healthcheck — `docker compose ps` shows it.
- External uptime: a free UptimeRobot monitor on `https://reportai.vazquezlabs.com/api/health`.
  It returns **503** when the database is unreachable, so any monitor that only looks at the
  status code catches it.
- Logs are one JSON object per line. Follow one report across its steps with
  `docker logs reportai_backend | grep '"report_id": "<uuid>"'` (every line inside a pipeline
  run carries `report_id` and `tenant_id`; failures include the traceback).
- Reports whose pipeline dies with the process (a deploy, a crash) are marked `failed`, and their
  sender is told, once they show no progress for `STUCK_REPORT_MINUTES` (15). A stop-gap until
  reports run on a durable queue.
