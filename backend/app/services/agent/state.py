import uuid
from typing import Any

from pydantic import BaseModel


class ToolUsage(BaseModel):
    """Side channel the execution-logging decorator reads and clears after each node."""

    model_used: str | None = None
    cost_usd: float | None = None


class DocumentTypeOption(BaseModel):
    id: uuid.UUID
    name: str


class AgentState(BaseModel):
    """Explicit, typed state for the report-generation graph — never an untyped dict."""

    thread_id: str  # = str(report_id), the LangGraph checkpoint key
    tenant_id: uuid.UUID
    channel_connection_id: uuid.UUID
    channel_type: str
    sender_id: str
    report_id: uuid.UUID

    raw_payload: dict[str, Any]
    incoming_text: str | None = None
    media_reference: str | None = None
    is_voice: bool = False
    media_local_path: str | None = None
    transcript: str | None = None

    document_type_id: uuid.UUID | None = None
    document_type_name: str | None = None
    field_schema: dict[str, Any] | None = None
    prompt_instructions: str | None = None
    notification_emails: list[str] = []
    available_document_types: list[DocumentTypeOption] = []
    doctype_selection_attempts: int = 0

    extracted_fields: dict[str, Any] | None = None
    extraction_attempts: int = 0
    last_validation_error: str | None = None
    correction_text: str | None = None
    correction_attempts: int = 0
    pending_user_reply: str | None = None

    rendered_docx_path: str | None = None
    rendered_pdf_path: str | None = None

    error_detail: str | None = None
    last_tool_usage: ToolUsage | None = None
