# syntax=docker/dockerfile:1
# Base images are pinned by digest so a rebuild can't silently change them; bump the digests
# deliberately (Renovate/Dependabot) together with uv.lock.
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

# ── Builder stage: includes dev tooling (ruff, mypy, pytest) ────────────────
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The venv lives outside /app so the dev compose's bind mount of ./backend doesn't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --frozen --extra dev --no-install-project

COPY app ./app/
COPY alembic.ini ./
COPY alembic ./alembic/

RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --frozen --extra dev

# ── Runtime stage: lean, no dev tooling, non-root user ──────────────────────
FROM python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS runtime

# The release this image is (set by the publish workflow): shown in the panel and compared with
# the latest release to tell the installation's administrator an update is out.
ARG REPORTAI_VERSION=dev
ENV REPORTAI_VERSION=$REPORTAI_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app/
COPY alembic.ini ./
COPY alembic ./alembic/
COPY scripts ./scripts/

RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev --no-editable

# /app/storage must exist and belong to appuser *before* the volume is mounted on it: Docker
# seeds a new named volume with the image directory's ownership, and without this it is
# root-owned and the app can't write a single template, audio or PDF.
RUN useradd --create-home appuser \
    && mkdir -p /app/storage \
    && chown -R appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Traefik is the only way in; trusting its X-Forwarded-For lets the login rate limiter see
# real client IPs instead of counting every user as the proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
