import uuid
from pathlib import Path
from typing import Any, ClassVar

from app.services.channels.base import (
    ChannelAdapter,
    ChannelAdapterError,
    IncomingMessage,
    OutgoingMessage,
)
from app.services.delivery.email import send_report_email


class EmailInboundAdapter(ChannelAdapter):
    """Unlike Telegram/WhatsApp, Mailgun pushes attachment bytes in the same webhook POST —
    the route already writes them to local storage before calling receive_message(), so
    media_reference is a local path and download_media() is a plain disk read."""

    channel_type: ClassVar[str] = "email"

    def __init__(self, inbound_slug: str, channel_connection_id: uuid.UUID) -> None:
        self._inbound_slug = inbound_slug
        self._connection_id = channel_connection_id

    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        sender = payload.get("sender")
        if not sender:
            raise ChannelAdapterError(f"Unsupported inbound email payload: {payload!r}")

        return IncomingMessage(
            channel_type=self.channel_type,
            channel_connection_id=self._connection_id,
            sender_id=sender,
            text=payload.get("stripped_text") or payload.get("body_plain"),
            media_reference=payload.get("saved_attachment_path"),
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        if not message.attachments:
            # Plain-text-only reply: reuse the SMTP relay with no attachment by sending an
            # empty placeholder file would be wrong — this channel is confirmation-by-reply
            # only meaningfully once there's a PDF, which always comes with attachments=[...].
            return
        await send_report_email(
            to=[message.recipient_id],
            subject="ReportAI",
            body=message.text,
            attachment_path=message.attachments[0],
        )

    async def download_media(self, media_reference: str) -> bytes:
        return Path(media_reference).read_bytes()
