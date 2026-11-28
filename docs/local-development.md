# Local development

## Prerequisites

- Docker + Docker Compose
- `make`

## Setup

1. Copy the env file and fill in real values:
   ```
   cp .env.example .env
   ```
   Generate `SECRET_KEY` with:
   ```
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Start Postgres and the backend:
   ```
   make up
   ```

3. Apply database migrations:
   ```
   make migrate
   ```

4. Check it's alive:
   ```
   curl localhost:8000/health
   ```

## Exercising the agent pipeline (Phase 1)

```
make seed-demo   # demo tenant, one document type, a self-generated template
```

The commands below run from the repository root, where the dev compose file is not the default
one, so name it once:
```
COMPOSE="docker compose --project-directory . -f infra/docker-compose.yml"
```

Get the demo Telegram connection id and its webhook secret (seeded connections
carry one, and the route rejects requests without it), let the simulated sender
in (a connection with an empty allow-list refuses everyone unless
`ALLOW_ANY_SENDER=true`), and simulate an incoming text message:
```
CONN_ID=$($COMPOSE exec -T postgres psql -U reportai -d reportai -tAc \
  "select id from channel_connections where channel_type='telegram' limit 1;")
SECRET=$($COMPOSE exec -T postgres psql -U reportai -d reportai -tAc \
  "select credentials->>'secret_token' from channel_connections where id='${CONN_ID}';")
$COMPOSE exec -T postgres psql -U reportai -d reportai -c \
  "update channel_connections set allowed_senders = '{123456}' where id='${CONN_ID}';"
curl -s -X POST "http://localhost:8000/webhooks/telegram/${CONN_ID}" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -d '{"message":{"chat":{"id":123456},"text":"Meeting today with Ana and Luis, discussed Q3 budget, action item: send proposal by Friday"}}'
```
Expect an immediate `200` — the webhook only records the message and a job; the `worker` service runs the pipeline.

Watch it progress node by node:
```
watch -n1 'docker compose --project-directory . -f infra/docker-compose.yml exec -T postgres psql -U reportai -d reportai -c \
  "select step, status, model_used, cost_usd, latency_ms, created_at from execution_logs order by created_at desc limit 15;"'
```
It should end on a `status=interrupted` row for `await_human_approval` — the pipeline is waiting for a reply, not stuck or errored. Confirm the pause is real and durable:
```
$COMPOSE exec -T postgres psql -U reportai -d reportai -c "select id, status from reports order by created_at desc limit 1;"
# expect status = 'awaiting_approval'
$COMPOSE restart worker   # proves the checkpoint lives in Postgres, not in the worker's memory
```
Reply to resume:
```
curl -s -X POST "http://localhost:8000/webhooks/telegram/${CONN_ID}" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -d '{"message":{"chat":{"id":123456},"text":"CONFIRM"}}'
```
Alternatively, review it in the panel (`/admin/reports`, then the report): the
page shows what was said (text, audio, photos), each extracted field with the
quote it came from, where every copy was sent, and the timeline. From there you
can approve with corrections, preview the PDF, reject with a reason the
requester receives, correct a delivered report and regenerate its PDF, or send
a copy again or to another address.

Every email the app sends in development (report copies, password resets,
invitations) lands in Mailpit instead of a real inbox: open
http://localhost:8025 to read them, attachments included.

## Common commands

Run `make help` for the full list. The most-used ones:

- `make logs` — tail logs from all services
- `make test` — run the backend test suite (fast, free, excludes the golden-set eval)
- `make eval` — run the golden-set extraction eval (costs real AI provider API calls, about 1 USD): 83 generated cases with known answers; it fails if field accuracy drops below 90% or any field is invented
- `make lint` — run ruff + mypy
- `make seed-demo` — seed a demo tenant with a self-generated document template
- `make migrate-create MSG="add reports table"` — generate a new Alembic revision (review the diff manually before applying — never blind-autogenerate-and-apply)
- `make shell-db` — open a psql shell against the dev database
- `make down` — stop everything
- `make hooks` — once per clone: enables `.githooks/pre-commit` (ruff + mypy when `backend/` is staged, eslint when `frontend/` is staged)

## Checks without Docker for the app

Backend, from `backend/`:

- `uv run --extra dev ruff check .` and `uv run --extra dev mypy app` need no database.
- Everything else reads its settings from the environment and needs the compose `postgres` up:
  `export POSTGRES_HOST=localhost UV_ENV_FILE=../.env` (shell variables win over the file; on the
  host also point `DOCUMENT_STORAGE_PATH` at a writable directory, since `.env` names the
  container's), then `uv run --extra dev alembic upgrade head && uv run --extra dev alembic check`
  and `uv run --extra dev pytest -m "not eval"`. The suite creates
  `<POSTGRES_DB>_test_<checkout hash>` and drops it when it ends, one database per checkout: runs in different worktrees
  against the same Postgres don't touch each other, two runs in the same checkout still do. Between
  tests it empties every table with `DELETE` in one transaction (`tests/conftest.py`), which keeps
  commits real for the tests that read from another connection.
- ruff format is not enforced: don't reformat files you aren't otherwise changing.

Frontend, from `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`, and
`npm run test:e2e` for the main flow in Chromium (Playwright) against
`infra/docker-compose.e2e.yml` — production images with the AI provider replaced by
`infra/e2e/ai_stub.py`; start it with `docker compose -f infra/docker-compose.e2e.yml up -d --build
--wait` and seed it with `... run --rm seed`.

CI (`.github/workflows/ci.yml`) runs all of the above except the paid eval, plus the production
builds. The eval and how to publish a run: [`evals.md`](evals.md).

## Invariants

The rules below are for changing the code; why the system relies on them is in
[Architecture, invariants](architecture.md#invariants).

- **Tenant isolation.** Every company-scoped route takes the company from the signed-in user
  (`require_tenant_id`) and loads rows with `get_scoped_or_404` (`backend/app/core/scoping.py`).
  Another company's row is a 404, never a 403 (a 403 confirms the id exists). A company id never
  comes from the request body or query. Every new route with an id in its path joins the matrix in
  `backend/tests/test_tenant_isolation.py`.
- **Self-host must not change.** New feature flags default to off; a `SINGLE_TENANT=true`
  installation behaves exactly as before; new columns get neutral defaults so existing rows stay
  valid.
- **i18n.** Every message a person sees from the backend goes through
  `backend/app/services/i18n.py`, in `es` and `en` (`tests/test_i18n.py` checks keys and
  placeholders); panel strings go in both locale folders.
- **Migrations.** Files are `YYYYMMDD_NNNN_<slug>.py` with sequential revision ids (`"0034"`
  revises `"0033"`). Review autogenerated diffs by hand. Data migrations inline what they need
  instead of importing app code.
- **Secrets.** Never log Telegram Bot API URLs or tokens (the URL carries the token; httpx is held
  at WARNING for this reason), and never print `.env` values.
- **Errors fail loud.** No `try/except` that swallows an exception; catch only what you handle.
- **Shortcuts are labelled.** A deliberate simplification carries a `ponytail:` comment naming its
  ceiling and the upgrade path.
- **Dependencies.** A new Python or npm dependency needs the owner's approval first.
- **Commits.** English, imperative, one logical change each, with a conventional prefix and an
  optional scope: `feat:`, `fix(landing):`, `chore(database):`, `ci:`, `docs:`.
