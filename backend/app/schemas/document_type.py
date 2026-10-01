import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.validators import EmailField

# Must match app.services.agent.tools.extraction_schema.FIELD_TYPES exactly — an unsupported
# type here would only fail later, at extraction time, on a real request.
FieldType = Literal[
    "str", "int", "float", "bool", "date", "time", "email", "phone",
    "list[str]", "list[int]", "enum", "list[object]", "image",
]
ColumnType = Literal["str", "int", "float", "bool", "date", "time", "email", "phone"]


class ColumnSpec(BaseModel):
    type: ColumnType
    description: str = ""


class FieldSchemaEntry(BaseModel):
    type: FieldType
    description: str = ""
    # "Required to send": the bot asks for it when the message doesn't contain it.
    required: bool = True
    label: str | None = Field(default=None, max_length=120)
    options: list[str] | None = None  # enum only
    columns: dict[str, ColumnSpec] | None = None  # list[object] (a table) only
    multiple: bool | None = None  # image only: one slot for several photos

    @model_validator(mode="after")
    def _check_type_specific_keys(self) -> Self:
        if self.type == "enum":
            if not self.options or len(set(self.options)) < 2:
                raise ValueError("an enum field needs at least two different options")
        elif self.options is not None:
            raise ValueError("options only apply to enum fields")
        if self.type == "list[object]":
            if not self.columns:
                raise ValueError("a table field needs at least one column")
        elif self.columns is not None:
            raise ValueError("columns only apply to list[object] fields")
        if self.multiple is not None and self.type != "image":
            raise ValueError("multiple only applies to image fields")
        return self


def _no_reserved_field_names(field_schema: dict[str, "FieldSchemaEntry"]) -> dict[str, "FieldSchemaEntry"]:
    # Templates use {{ branding.* }} for the company's name, colour and logo.
    if "branding" in field_schema:
        raise ValueError("'branding' is reserved for the company's logo and name in templates; rename that field")
    return field_schema


FieldSchema = Annotated[dict[str, "FieldSchemaEntry"], AfterValidator(_no_reserved_field_names)]


class DocumentTypeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    field_schema: FieldSchema = Field(default_factory=dict)
    prompt_instructions: str | None = None
    notification_emails: list[EmailField] = Field(default_factory=list)


class DocumentTypeUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    field_schema: FieldSchema = Field(default_factory=dict)
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
