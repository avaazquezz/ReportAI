import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import EmailField


class ReportResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    document_type_id: uuid.UUID | None
    document_type_name: str | None
    status: str
    requester_channel: str
    requester_identifier: str
    error_detail: str | None
    download_url: str | None
    created_at: datetime
    completed_at: datetime | None


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    destination: str
    status: str
    attempts: int
    last_error: str | None
    sent_at: datetime | None
    updated_at: datetime


class StepResponse(BaseModel):
    """One pipeline step, from execution_logs: the machine's side of the timeline."""

    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str
    latency_ms: int | None
    cost_usd: float | None
    error_detail: str | None
    created_at: datetime


class RevisionResponse(BaseModel):
    """One thing a person did from the panel: the human side of the timeline."""

    action: str
    user_name: str | None
    changes: dict[str, Any] | None
    note: str | None
    created_at: datetime


class PhotoResponse(BaseModel):
    id: uuid.UUID
    url: str
    caption: str | None


class ReportDetailResponse(ReportResponse):
    """Everything a reviewer needs on one page: what was said (text or audio), what was extracted
    and the quote backing each field, the schema to edit it against, the photos, where each copy
    went, and the timeline of what the pipeline and people did."""

    received_at: datetime | None
    updated_at: datetime
    source_text: str | None
    audio_url: str | None
    reject_reason: str | None
    extracted_fields: dict[str, Any] | None
    evidence: dict[str, Any] | None
    field_schema: dict[str, Any] | None
    photos: list[PhotoResponse]
    deliveries: list[DeliveryResponse]
    steps: list[StepResponse]
    revisions: list[RevisionResponse]


class ApproveRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class EditFieldsRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class ResendRequest(BaseModel):
    """No body: every copy that failed. A delivery id: that copy again. An email: a copy to it."""

    delivery_id: uuid.UUID | None = None
    email: EmailField | None = None
