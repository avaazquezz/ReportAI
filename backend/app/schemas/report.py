import uuid
from datetime import datetime

from pydantic import BaseModel


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
