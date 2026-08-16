# ── Builder stage: includes dev tooling (ruff, mypy, pytest) ────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app/
COPY alembic.ini ./
COPY alembic ./alembic/

RUN pip install --no-cache-dir -e ".[dev]"

# ── Runtime stage: lean, no dev tooling, non-root user ──────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app/
COPY alembic.ini ./
COPY alembic ./alembic/
COPY scripts ./scripts/

RUN pip install --no-cache-dir . \
    && useradd --create-home appuser \
    && chown -R appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
