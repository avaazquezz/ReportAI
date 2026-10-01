import uuid
from email.utils import parseaddr
from pathlib import Path
from typing import Any, ClassVar

from app.services.channels.base import (
    ChannelAdapter,
    ChannelAdapterError,
    IncomingMessage,
    OutgoingMessage,
)
from app.services.delivery.email import send_report_email
from app.services.notifications.email import send_plain_email


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
            external_id=payload.get("message_id"),
            sender_label=parseaddr(payload.get("from") or "")[0] or None,
            # What a reply needs to stay in the same thread in the person's mail client.
            meta={"message_id": payload.get("message_id"), "subject": payload.get("subject")},
            raw_payload=payload,
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        """Answers in the person's own thread, so the recap, the question and the PDF all stay
        under the email they sent — a reply to any of them reaches the same report."""
        original_id = message.meta.get("message_id")
        subject = message.meta.get("subject") or "ReportAI"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        headers = {"In-Reply-To": original_id, "References": original_id} if original_id else {}
        if message.attachments:
            await send_report_email(
                to=[message.recipient_id],
                subject=subject,
                body=message.text,
                attachment_path=message.attachments[0],
                attachment_name=message.attachment_name,
                headers=headers,
            )
        else:
            await send_plain_email(to=[message.recipient_id], subject=subject, body=message.text, headers=headers)

    async def download_media(self, media_reference: str) -> bytes:
        return Path(media_reference).read_bytes()
