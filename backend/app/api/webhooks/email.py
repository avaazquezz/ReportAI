import hashlib
import hmac
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.channel_connection import ChannelConnection
from app.services.agent.invoke import start_or_resume_pipeline
from app.services.channels.email_inbound import EmailInboundAdapter

router = APIRouter(tags=["webhooks"])
logger = logging.getLogger(__name__)

_AUDIO_CONTENT_TYPES = {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm"}


def _verify_signature(timestamp: str, token: str, signature: str) -> bool:
    expected = hmac.new(
        settings.MAILGUN_SIGNING_KEY.encode(), f"{timestamp}{token}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/email")
async def email_webhook(
    request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    form = await request.form()

    if not _verify_signature(
        str(form.get("timestamp", "")), str(form.get("token", "")), str(form.get("signature", ""))
    ):
        logger.warning("Mailgun webhook signature verification failed")
        return {"status": "ignored"}

    recipient = str(form.get("recipient", ""))
    inbound_slug = recipient.split("@", 1)[0] if "@" in recipient else recipient
    if not inbound_slug:
        return {"status": "ignored"}

    result = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.channel_type == "email",
            ChannelConnection.credentials["inbound_slug"].astext == inbound_slug,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        logger.warning("No email connection for inbound_slug=%s", inbound_slug)
        return {"status": "ignored"}

    saved_attachment_path: str | None = None
    for value in form.values():
        if isinstance(value, UploadFile) and value.content_type in _AUDIO_CONTENT_TYPES:
            storage_dir = Path(settings.DOCUMENT_STORAGE_PATH) / "inbound_tmp"
            storage_dir.mkdir(parents=True, exist_ok=True)
            dest = storage_dir / f"{uuid.uuid4()}.audio"
            dest.write_bytes(await value.read())
            saved_attachment_path = str(dest)
            break

    payload = {
        "sender": str(form.get("sender", "")),
        "stripped_text": str(form.get("stripped-text", "")) or None,
        "body_plain": str(form.get("body-plain", "")) or None,
        "saved_attachment_path": saved_attachment_path,
    }

    adapter = EmailInboundAdapter(
        inbound_slug=connection.credentials["inbound_slug"], channel_connection_id=connection.id
    )
    try:
        incoming = await adapter.receive_message(payload)
    except Exception:  # noqa: BLE001 — must not raise on a malformed inbound email
        logger.exception("Failed to parse inbound email payload")
        return {"status": "ignored"}

    await start_or_resume_pipeline(
        db=db, connection=connection, incoming=incoming, background_tasks=background_tasks
    )
    return {"status": "ok"}
