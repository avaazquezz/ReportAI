COMPOSE = docker compose --project-directory . -f infra/docker-compose.yml

.PHONY: help up down logs ps shell-db migrate migrate-down migrate-create test lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the local dev environment
	$(COMPOSE) up --build -d

down: ## Stop the local dev environment
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

ps: ## Show running services
	$(COMPOSE) ps

shell-db: ## Open a psql shell against the dev database
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-reportai} -d $${POSTGRES_DB:-reportai}

migrate: ## Apply all pending Alembic migrations
	$(COMPOSE) exec backend alembic upgrade head

migrate-down: ## Revert the last Alembic migration
	$(COMPOSE) exec backend alembic downgrade -1

migrate-create: ## Create a new migration: make migrate-create MSG="add reports table"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(MSG)"

test: ## Run the backend test suite (fast, free, deterministic)
	$(COMPOSE) exec backend pytest -v -m "not eval"

eval: ## Run the golden-set eval suite (costs real Anthropic/Groq API calls)
	$(COMPOSE) exec backend pytest -v -m eval

lint: ## Run ruff and mypy against the backend
	$(COMPOSE) exec backend sh -c "ruff check . && mypy app"

seed-demo: ## Seed a demo tenant with a self-generated template
	$(COMPOSE) exec backend python scripts/seed_demo_tenant.py

set-webhook: ## Register the Telegram webhook with the Bot API (needs PUBLIC_BASE_URL)
	$(COMPOSE) exec backend python scripts/set_telegram_webhook.py
