import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    document_type_id: uuid.UUID
    original_filename: str
    version: int
    is_active: bool
    uploaded_by: uuid.UUID | None
    created_at: datetime
