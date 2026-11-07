"""The ReportAI app as a channel: a technician records in the browser and reviews the result on
screen, so there is no one to message back. Captures arrive through POST /capture, not a webhook.

Each company gets one `web` connection, made on its first capture, so reports, the graph and the
worker treat the app like any other channel."""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.models.channel_connection import ChannelConnection
from app.services.channels.base import ChannelAdapter, IncomingMessage, OutgoingMessage
from app.services.transcription import AUDIO_TYPES

WEB = "web"
_AUDIO_SUFFIXES = {content_type: suffix for suffix, content_type in AUDIO_TYPES.items()}


async def store_voice_note(upload: UploadFile) -> str:
    """Keeps a recording sent from the app until its job copies it into the report (inbound_tmp is
    swept after two days). Returns the path, which is the media_reference. The extension follows
    the browser's format: Chrome records webm, Safari mp4."""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    suffix = _AUDIO_SUFFIXES.get(content_type)
    if suffix is None:
        raise ValidationException(f"Unsupported audio format: {content_type or 'unknown'}")
    data = await upload.read(settings.MAX_AUDIO_BYTES + 1)
    if len(data) > settings.MAX_AUDIO_BYTES:
        raise ValidationException(f"The recording is over the {settings.MAX_AUDIO_BYTES // (1024 * 1024)} MB limit")
    folder = Path(settings.DOCUMENT_STORAGE_PATH) / "inbound_tmp"
    path = folder / f"{uuid.uuid4()}{suffix}"

    def _write() -> None:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    await asyncio.to_thread(_write)
    return str(path)


class WebAdapter(ChannelAdapter):
    """media_reference is a local path (the uploaded voice note); the person reads every answer
    in the app, so sending is a no-op."""

    channel_type = WEB

    def __init__(self, channel_connection_id: uuid.UUID) -> None:
        self.channel_connection_id = channel_connection_id

    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError("The app sends its captures to POST /capture")

    async def send_message(self, message: OutgoingMessage) -> None:
        return None

    async def download_media(self, media_reference: str) -> bytes:
        return Path(media_reference).read_bytes()


async def web_connection(db: AsyncSession, tenant_id: uuid.UUID) -> ChannelConnection:
    """The company's app connection, made on first use. The routing key is the company, so the
    unique (channel_type, routing_key) constraint keeps it to one even under concurrent captures."""
    routing_key = str(tenant_id)
    await db.execute(
        pg_insert(ChannelConnection)
        .values(
            tenant_id=tenant_id, channel_type=WEB, display_name="App", routing_key=routing_key,
            credentials={}, allowed_senders=[], is_active=True,
        )
        .on_conflict_do_nothing(constraint="uq_channel_connections_type_routing_key")
    )
    return (
        await db.scalars(
            select(ChannelConnection).where(ChannelConnection.channel_type == WEB, ChannelConnection.routing_key == routing_key)
        )
    ).one()
