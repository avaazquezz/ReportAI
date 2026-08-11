import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import EmailField


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=255)
    admin_email: EmailField
    admin_full_name: str = Field(min_length=1, max_length=255)


class TenantUpdateRequest(BaseModel):
    is_active: bool


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class TenantCreateResponse(TenantResponse):
    invite_email_sent: bool
