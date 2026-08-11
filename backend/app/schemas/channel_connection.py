import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

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


class ChannelConnectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_type: str
    display_name: str
    has_credentials: bool
    allowed_senders: list[str]
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, connection: ChannelConnection) -> "ChannelConnectionResponse":
        """Never exposes raw credential values — only whether any are set."""
        return cls(
            id=connection.id,
            tenant_id=connection.tenant_id,
            channel_type=connection.channel_type,
            display_name=connection.display_name,
            has_credentials=bool(connection.credentials),
            allowed_senders=connection.allowed_senders,
            is_active=connection.is_active,
            created_at=connection.created_at,
        )
