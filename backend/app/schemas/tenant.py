import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import EmailField


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=255)
    admin_email: EmailField
    admin_full_name: str = Field(min_length=1, max_length=255)


PlanKey = Literal["unlimited", "trial", "starter", "pro", "business"]  # services/plans.py PLANS
PlanStatus = Literal["trialing", "active", "past_due", "canceled"]


class TenantUpdateRequest(BaseModel):
    """Changing `plan` starts a new period from now; changing only `plan_status` keeps it."""

    is_active: bool | None = None
    plan: PlanKey | None = None
    plan_status: PlanStatus | None = None


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    plan: str
    plan_status: str
    plan_period_end: datetime | None
    created_at: datetime


class TenantCreateResponse(TenantResponse):
    invite_email_sent: bool
