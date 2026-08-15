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

Get the demo Telegram connection id and its webhook secret (seeded connections
carry one, and the route rejects requests without it) and simulate an incoming
text message:
```
CONN_ID=$(docker compose exec postgres psql -U reportai -d reportai -tAc \
  "select id from channel_connections where channel_type='telegram' limit 1;")
SECRET=$(docker compose exec postgres psql -U reportai -d reportai -tAc \
  "select credentials->>'secret_token' from channel_connections where id='${CONN_ID}';")
curl -s -X POST "http://localhost:8000/webhooks/telegram/${CONN_ID}" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -d '{"message":{"chat":{"id":123456},"text":"Meeting today with Ana and Luis, discussed Q3 budget, action item: send proposal by Friday"}}'
```
Expect an immediate `200` — the pipeline runs in a background task, proving the webhook isn't blocked on it.

Watch it progress node by node:
```
watch -n1 'docker compose exec postgres psql -U reportai -d reportai -c \
  "select step, status, model_used, cost_usd, latency_ms, created_at from execution_logs order by created_at desc limit 15;"'
```
It should end on a `status=interrupted` row for `await_human_approval` — the pipeline is waiting for a reply, not stuck or errored. Confirm the pause is real and durable:
```
docker compose exec postgres psql -U reportai -d reportai -c "select id, status from reports order by created_at desc limit 1;"
# expect status = 'awaiting_approval'
docker compose restart backend   # proves the checkpoint lives in Postgres, not process memory
```
Reply to resume:
```
curl -s -X POST "http://localhost:8000/webhooks/telegram/${CONN_ID}" \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -d '{"message":{"chat":{"id":123456},"text":"CONFIRM"}}'
```
Alternatively, approve from the API instead of the channel (the recovery path
when the approval prompt never reached the requester): log in as the demo user
and `POST /reports/{id}/approve`.

With dev placeholder credentials the run ends `failed` at `deliver_email`
(fake SMTP host) — expected; everything up to and including rendering the PDF
via Gotenberg is still verified in the `execution_logs` trail.

## Common commands

Run `make help` for the full list. The most-used ones:

- `make logs` — tail logs from all services
- `make test` — run the backend test suite (fast, free, excludes the golden-set eval)
- `make eval` — run the golden-set extraction eval (costs real Anthropic/Groq API calls)
- `make lint` — run ruff + mypy
- `make seed-demo` — seed a demo tenant with a self-generated document template
- `make migrate-create MSG="add reports table"` — generate a new Alembic revision (review the diff manually before applying — never blind-autogenerate-and-apply)
- `make shell-db` — open a psql shell against the dev database
- `make down` — stop everything
