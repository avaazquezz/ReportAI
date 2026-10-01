import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.channel_connection import ChannelConnection

ChannelType = Literal["telegram", "whatsapp", "email"]

# Must match the credential keys app.services.channels.factory.get_channel_adapter
# actually reads — catches a malformed connection here, not as a KeyError deep in
# message delivery.
REQUIRED_CREDENTIAL_KEYS: dict[str, set[str]] = {
    "telegram": {"bot_token"},
    "whatsapp": {"phone_number_id", "access_token"},
    "email": {"inbound_slug"},
}


# The credential a shared webhook routes on (channel_connections.routing_key).
ROUTING_CREDENTIAL: dict[str, str] = {"whatsapp": "phone_number_id", "email": "inbound_slug"}


def routing_key_for(channel_type: str, credentials: dict[str, str]) -> str | None:
    key = ROUTING_CREDENTIAL.get(channel_type)
    return credentials.get(key) if key else None


class ChannelConnectionCreateRequest(BaseModel):
    channel_type: ChannelType
    display_name: str = Field(min_length=1, max_length=255)
    credentials: dict[str, str]
    allowed_senders: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_required_credentials(self) -> Self:
        required = REQUIRED_CREDENTIAL_KEYS[self.channel_type]
        missing = required - self.credentials.keys()
        if missing:
            raise ValueError(
                f"Missing required credential(s) for {self.channel_type}: {sorted(missing)}"
            )
        return self


class ChannelConnectionUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    # Merged into the existing credentials, not a full replacement — omit a key to
    # leave it unchanged, so the caller never needs to resupply a secret it already set.
    credentials: dict[str, str] | None = None
    allowed_senders: list[str] = Field(default_factory=list)
    is_active: bool = True


class SenderInviteCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=255)


class SenderInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    expires_at: datetime
    used_at: datetime | None
    sender_id: str | None
    created_at: datetime


class SenderInviteCreatedResponse(SenderInviteResponse):
    code: str  # shown once: only its hash is kept
    link: str | None  # Telegram: opening it is all the person has to do


class ChannelConnectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_type: str
    display_name: str
    has_credentials: bool
    bot_username: str | None = None  # Telegram: the bot people write to, @username
    allowed_senders: list[str]
    # Who an allowed sender is, by the name their invitation was made for.
    sender_labels: dict[str, str] = {}
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(
        cls, connection: ChannelConnection, sender_labels: dict[str, str] | None = None
    ) -> "ChannelConnectionResponse":
        """Never exposes raw credential values — only whether any are set."""
        return cls(
            id=connection.id,
            tenant_id=connection.tenant_id,
            channel_type=connection.channel_type,
            display_name=connection.display_name,
            has_credentials=bool(connection.credentials),
            bot_username=connection.credentials.get("bot_username"),
            allowed_senders=connection.allowed_senders,
            sender_labels=sender_labels or {},
            is_active=connection.is_active,
            created_at=connection.created_at,
        )
