# Infra

- `docker-compose.yml` — local development (hot reload, Postgres port exposed, source bind-mounted). Run via the root `Makefile`.
- `docker-compose.prod.yml` — private-server deployment behind Traefik. Assumes an external `web` Docker network and a Traefik certificate resolver named `le` already exist on the server. Single-domain routing: `${APP_DOMAIN}/api/*` → backend (StripPrefix + `API_ROOT_PATH=/api`), everything else → the Nuxt frontend.

## Production deploy runbook

Prerequisites on the server: Docker + Compose, the shared Traefik already running
on the external `web` network with a certificate resolver named `le`.

### 1. Domain — `reportai.vazquezdev.pro`

`reportai.is-a.dev` was the original plan (see the 2026-08-13 decisions-log
entry) but is-a.dev's Terms of Service rule it out on multiple counts:
commercial/for-profit use is explicitly prohibited (§4.8), AI-agent products
are called out by name as disallowed (§4.15), and PRs authored by an AI
coding tool are explicitly rejected on sight (§5) — see the 2026-08-16
decisions-log entry. Using a subdomain of `vazquezdev.pro` (already owned,
already pointed at this server for the portfolio site) avoids all three: add
an `A` record for `reportai` → the server's IP through whatever DNS host
manages `vazquezdev.pro` (nameservers `ns1/ns2.dns-parking.com` at the time
of writing). No external review, no separate registration step.

### 2. Server checkout + environment

```bash
cd /home/vazquezdev/proyectos   # convention this server already uses for every other project
git clone https://github.com/avaazquezz/ReportAI.git && cd ReportAI
cp .env.example .env   # then fill EVERY value with real production secrets
```

Production-specific values (see the commented blocks at the bottom of
`.env.example`): `APP_DOMAIN`, `API_ROOT_PATH=/api`, `FRONTEND_ORIGIN`,
`PUBLIC_BASE_URL`, `ENVIRONMENT=production`, the `DEMO_*` trio, and the guards
(`SENDER_RATE_LIMIT_PER_HOUR`, `DAILY_SPEND_CAP_USD`). Generate `SECRET_KEY`
and `DEMO_USER_PASSWORD` fresh — never reuse dev values. `.env` lives only on
the server; it is never committed.

### 3. Bring the stack up

```bash
docker compose --project-directory . -f infra/docker-compose.prod.yml up -d --build
docker compose --project-directory . -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

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

`curl https://reportai.vazquezdev.pro/api/health` returns 200, and the
landing page loads with its static demo audio/PDF playing and the language
auto-detecting/toggling correctly. No Telegram round-trip test — the bot
stays off (see above).

### 5. Cron jobs (host crontab)

```cron
# Nightly Postgres backup, 7-day rotation ($POSTGRES_* resolve inside the container)
30 4 * * * docker exec reportai_postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > /var/backups/reportai/reportai-$(date +\%u).sql.gz
```

(`%u` = day of week 1–7, so the rotation overwrites itself weekly. Create
`/var/backups/reportai` first.) No demo-reset cron line — there is no demo
tenant to reset while the public demo stays dormant.

### 6. Monitoring (minimal, deliberate)

- Container health: every service defines a Docker healthcheck — `docker compose ps` shows it.
- External uptime: a free UptimeRobot monitor on `https://reportai.vazquezdev.pro/api/health`.
