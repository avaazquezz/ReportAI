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

## Common commands

Run `make help` for the full list. The most-used ones:

- `make logs` — tail logs from all services
- `make test` — run the backend test suite
- `make lint` — run ruff + mypy
- `make migrate-create MSG="add reports table"` — generate a new Alembic revision (review the diff manually before applying — never blind-autogenerate-and-apply)
- `make shell-db` — open a psql shell against the dev database
- `make down` — stop everything
