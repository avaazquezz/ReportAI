import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import EmailField

# Must match app.services.agent.tools.extraction_schema._TYPE_MAP exactly — an
# unsupported type here would only fail later, at extraction time, on a real request.
FieldType = Literal["str", "int", "float", "bool", "date", "list[str]", "list[int]"]


class FieldSchemaEntry(BaseModel):
    type: FieldType
    description: str = ""
    required: bool = True


class DocumentTypeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    field_schema: dict[str, FieldSchemaEntry] = Field(default_factory=dict)
    prompt_instructions: str | None = None
    notification_emails: list[EmailField] = Field(default_factory=list)


class DocumentTypeUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    field_schema: dict[str, FieldSchemaEntry] = Field(default_factory=dict)
    prompt_instructions: str | None = None
    notification_emails: list[EmailField] = Field(default_factory=list)
    is_active: bool = True


class DocumentTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    field_schema: dict[str, FieldSchemaEntry]
    prompt_instructions: str | None
    notification_emails: list[str]
    is_active: bool
    created_at: datetime
