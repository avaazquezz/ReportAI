import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """A message received from any channel, normalized before it enters the agent pipeline."""

    channel_type: str
    channel_connection_id: uuid.UUID
    sender_id: str  # platform-specific user/chat id
    text: str | None = None
    media_reference: str | None = None  # opaque id/URL, passed back into download_media
    raw_payload: dict[str, Any]  # original webhook payload, kept for debugging

    # Webhooks are delivered at least once; this id (Telegram update_id, WhatsApp wamid, email
    # Message-Id) is what lets a redelivery be recognised and ignored.
    external_id: str | None = None
    sent_at: datetime | None = None
    sender_label: str | None = None  # a display name, for the model and for the panel
    photo_reference: str | None = None  # a picture to attach to the report
    unsupported: bool = False  # a sticker, a location... something the bot cannot use
    # A button the person pressed instead of typing: confirm | correct | cancel | doctype.
    action: str | None = None
    action_arg: str | None = None
    callback_id: str | None = None  # lets the channel acknowledge the press
    meta: dict[str, Any] = {}  # channel reply context, e.g. the email thread ids


class Button(BaseModel):
    """A choice offered as a tappable button where the channel supports it (Telegram); on the
    others the message text itself says how to reply."""

    label: str
    action: str  # confirm | correct | cancel | doctype
    arg: str | None = None


class OutgoingMessage(BaseModel):
    """A message to send back on the channel a request came in on."""

    recipient_id: str
    text: str
    attachments: list[str] | None = None
    attachment_name: str | None = None  # what the person sees the file called
    buttons: list[Button] | None = None
    meta: dict[str, Any] = {}  # channel reply context, e.g. the email thread to answer in


class ChannelAdapterError(Exception):
    """Raised on transport/credential/unsupported-media failures.

    Retry-with-backoff for transient failures belongs to the concrete Phase 1
    adapter implementation, not this contract.
    """


class ChannelAdapter(ABC):
    """One implementation per channel (Telegram, WhatsApp, email-in, ...).

    The agent pipeline decides *when* send_message fires (including whether a
    human-approval checkpoint sits before it) — this contract only defines
    *how* a channel receives and sends messages.
    """

    channel_type: ClassVar[str]

    @abstractmethod
    async def receive_message(self, payload: dict[str, Any]) -> IncomingMessage:
        """Parse a raw inbound webhook/event payload into a normalized IncomingMessage."""

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> None:
        """Send a message back on this channel."""

    @abstractmethod
    async def download_media(self, media_reference: str) -> bytes:
        """Resolve an IncomingMessage.media_reference into raw bytes (e.g. a voice note)."""

    async def acknowledge(self, callback_id: str) -> None:
        """Tell the channel a button press was received (stops Telegram's loading spinner)."""
