import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # Days until the key stops working; left out (or null), it never expires.
    expires_in_days: Literal[30, 90, 365] | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    owner_id: uuid.UUID
    owner_name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime | None  # None: never expires


class ApiKeyCreated(ApiKeyResponse):
    secret: str  # shown once: only its hash is kept
