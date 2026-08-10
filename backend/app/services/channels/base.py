import uuid
from abc import ABC, abstractmethod
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


class OutgoingMessage(BaseModel):
    """A message to send back on the channel a request came in on."""

    recipient_id: str
    text: str
    attachments: list[str] | None = None


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
