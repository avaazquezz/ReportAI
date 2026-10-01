import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import EmailField

TeamRole = Literal["tenant_admin", "approver", "viewer"]


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TeamInviteRequest(BaseModel):
    email: EmailField
    full_name: str = Field(min_length=1, max_length=255)
    role: TeamRole


class TeamInviteResponse(BaseModel):
    member: TeamMemberResponse
    invite_email_sent: bool
    # Only when the email could not be sent (no mail server yet): the admin passes it on by hand.
    invite_link: str | None = None


class TeamMemberUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: TeamRole | None = None
    is_active: bool | None = None
