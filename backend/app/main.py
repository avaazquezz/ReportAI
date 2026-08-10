from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api.webhooks import telegram as telegram_webhook
from app.api.webhooks import whatsapp as whatsapp_webhook
from app.core.config import settings
from app.core.langgraph_checkpointer import close_checkpointer, init_checkpointer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_checkpointer()
    yield
    await close_checkpointer()


app = FastAPI(title="ReportAI API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(telegram_webhook.router)
app.include_router(whatsapp_webhook.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "reportai-api", "environment": settings.ENVIRONMENT}
