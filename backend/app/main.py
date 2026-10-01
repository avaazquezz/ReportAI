import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, setup
from app.api.admin import channel_connections as admin_channel_connections
from app.api.admin import company as admin_company
from app.api.admin import document_types as admin_document_types
from app.api.admin import instance_settings as admin_instance_settings
from app.api.admin import reports as admin_reports
from app.api.admin import team as admin_team
from app.api.admin import tenants as admin_tenants
from app.api.admin import usage as admin_usage
from app.api.webhooks import email as email_webhook
from app.api.webhooks import telegram as telegram_webhook
from app.api.webhooks import whatsapp as whatsapp_webhook
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.services.agent.tools.pricing import require_priced_model_for_spend_cap
from app.services.setup import needs_setup

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    require_priced_model_for_spend_cap(settings.EXTRACTION_MODEL, settings.DAILY_SPEND_CAP_USD)
    async with AsyncSessionLocal() as session:
        if await needs_setup(session):
            logger.warning(
                "This installation is not set up yet: get a setup code with `reportai setup-code` "
                "and open %s/setup", settings.FRONTEND_ORIGIN
            )
    yield


# The interactive docs and the OpenAPI schema document every endpoint for whoever asks:
# they're a development tool, not something a production instance should publish.
_docs_enabled = settings.is_development

app = FastAPI(
    title="ReportAI API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    # Behind Traefik's StripPrefix in prod — keeps /docs, openapi.json and
    # trailing-slash redirects generating /api-prefixed URLs.
    root_path=settings.API_ROOT_PATH,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(setup.router)
app.include_router(admin_tenants.router)
app.include_router(admin_document_types.router)
app.include_router(admin_channel_connections.router)
app.include_router(admin_reports.router)
app.include_router(admin_usage.router)
app.include_router(admin_instance_settings.router)
app.include_router(admin_team.router)
app.include_router(admin_company.router)
app.include_router(telegram_webhook.router)
app.include_router(whatsapp_webhook.router)
app.include_router(email_webhook.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "reportai-api"}
