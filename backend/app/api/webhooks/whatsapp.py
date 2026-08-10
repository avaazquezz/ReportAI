import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationException
from app.models.channel_connection import ChannelConnection
from app.services.agent.invoke import start_or_resume_pipeline
from app.services.channels.whatsapp import WhatsAppAdapter

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.get("/webhooks/whatsapp")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> int:
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return int(hub_challenge)
    raise AuthenticationException("WhatsApp webhook verification failed")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    raw_body = await request.body()
    # WhatsApp disables a webhook after repeated non-2xx responses — always
    # return 200 fast, log resolution/signature failures instead of raising.
    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        logger.warning("WhatsApp webhook signature verification failed")
        return {"status": "ignored"}

    payload: dict[str, Any] = await request.json()
    try:
        phone_number_id = payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
    except (KeyError, IndexError):
        return {"status": "ignored"}

    result = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.channel_type == "whatsapp",
            ChannelConnection.credentials["phone_number_id"].astext == phone_number_id,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        logger.warning("No WhatsApp connection for phone_number_id=%s", phone_number_id)
        return {"status": "ignored"}

    adapter = WhatsAppAdapter(
        phone_number_id=connection.credentials["phone_number_id"],
        access_token=connection.credentials["access_token"],
        channel_connection_id=connection.id,
    )
    try:
        incoming = await adapter.receive_message(payload)
    except Exception:
        logger.exception("Failed to parse WhatsApp payload")
        return {"status": "ignored"}

    await start_or_resume_pipeline(
        db=db, connection=connection, incoming=incoming, background_tasks=background_tasks
    )
    return {"status": "ok"}
