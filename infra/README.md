# Infra

- `docker-compose.yml` — local development (hot reload, Postgres port exposed, source bind-mounted). Run via the root `Makefile`.
- `docker-compose.prod.yml` — private-server deployment behind Traefik. Assumes an external `web` Docker network and a Traefik certificate resolver named `le` already exist on the server. Single-domain routing: `${APP_DOMAIN}/api/*` → backend (StripPrefix + `API_ROOT_PATH=/api`), everything else → the Nuxt frontend.

## Production deploy runbook

Prerequisites on the server: Docker + Compose, the shared Traefik already running
on the external `web` network with a certificate resolver named `le`.

### 1. Domain — `reportai.is-a.dev`

Registered via a PR to [is-a-dev/register](https://github.com/is-a-dev/register):
fork the repo and add `domains/reportai.json` (A record pointing at the server,
no Cloudflare proxy — Traefik terminates TLS via Let's Encrypt):

```json
{
  "owner": {
    "username": "avaazquezz",
    "email": "adrianvazvaz.2117@gmail.com"
  },
  "records": {
    "A": ["<SERVER_IP>"]
  }
}
```

External review takes days — open this PR before anything else.

### 2. Server checkout + environment

```bash
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
docker compose --project-directory . -f infra/docker-compose.prod.yml exec backend python scripts/seed_demo_tenant.py
docker compose --project-directory . -f infra/docker-compose.prod.yml exec backend python scripts/set_telegram_webhook.py
```

### 4. Smoke test (the real thing, not curl)

Send a voice note to the demo Telegram bot → reply CONFIRM → the PDF comes back
on the channel and lands in the notification inbox. Then check the panel:
report visible with its cost in the usage dashboard, and a second run approved
from the panel instead of the channel.

### 5. Cron jobs (host crontab)

```cron
# Nightly demo reset — wipes the demo tenant (cascade) and re-seeds it clean
0 4 * * * cd /path/to/ReportAI && docker compose --project-directory . -f infra/docker-compose.prod.yml exec -T backend python scripts/seed_demo_tenant.py --reset

# Nightly Postgres backup, 7-day rotation ($POSTGRES_* resolve inside the container)
30 4 * * * docker exec reportai_postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > /var/backups/reportai/reportai-$(date +\%u).sql.gz
```

(`%u` = day of week 1–7, so the rotation overwrites itself weekly. Create
`/var/backups/reportai` first.)

The demo reset regenerates the Telegram `secret_token`, so re-register the
webhook after each reset — or append `&& docker compose ... exec -T backend
python scripts/set_telegram_webhook.py` to the reset cron line.

### 6. Monitoring (minimal, deliberate)

- Container health: every service defines a Docker healthcheck — `docker compose ps` shows it.
- External uptime: a free UptimeRobot monitor on `https://reportai.is-a.dev/api/health`.
