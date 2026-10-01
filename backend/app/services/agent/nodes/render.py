import asyncio
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document_template import DocumentTemplate
from app.models.report_attachment import ReportAttachment
from app.repositories.base import BaseRepository
from app.services.agent.state import AgentState
from app.services.agent.tools.extraction_schema import extractable_fields, image_fields
from app.services.observability.execution_log import observed_node
from app.services.rendering.docx_render import fill_template
from app.services.rendering.gotenberg_client import convert_docx_to_pdf


async def _load_active_template(document_type_id: object) -> DocumentTemplate:
    async with AsyncSessionLocal() as session:
        repo = BaseRepository(DocumentTemplate, session)
        templates = await repo.list(
            filters={"document_type_id": document_type_id, "is_active": True}, limit=1
        )
        if not templates:
            raise ValueError(f"No active template for document_type {document_type_id}")
        return templates[0]


async def _photo_paths(report_id: object) -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(ReportAttachment.path)
            .where(ReportAttachment.report_id == report_id)
            .order_by(ReportAttachment.created_at)
        )
        return list(rows)


def template_values(field_schema: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """A list or table nobody mentioned is null, and a template looping over it would crash:
    give it an empty list instead."""
    empty_lists: dict[str, list[Any]] = {
        name: []
        for name, spec in extractable_fields(field_schema).items()
        if str(spec.get("type", "")).startswith("list[") and fields.get(name) is None
    }
    return {**fields, **empty_lists}


def assign_photos(field_schema: dict[str, Any], photos: list[str]) -> dict[str, str | list[str] | None]:
    """Fills the photo slots in the order the schema lists them, with the photos in the order
    they arrived: a single slot takes the next one, a `multiple` slot takes all that are left."""
    remaining = list(photos)
    slots: dict[str, str | list[str] | None] = {}
    for name, spec in image_fields(field_schema).items():
        if spec.get("multiple"):
            slots[name], remaining = remaining, []
        else:
            slots[name] = remaining.pop(0) if remaining else None
    return slots


@observed_node("render")
async def render_node(state: AgentState) -> AgentState:
    assert state.extracted_fields is not None
    schema = state.field_schema or {}
    template = await _load_active_template(state.document_type_id)
    photos = assign_photos(schema, await _photo_paths(state.report_id)) if image_fields(schema) else {}
    output_path = f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.docx"
    docx_path = await asyncio.to_thread(
        fill_template, template.file_path, template_values(schema, state.extracted_fields), output_path, photos
    )
    return state.model_copy(update={"rendered_docx_path": docx_path})


@observed_node("convert_pdf")
async def convert_pdf_node(state: AgentState) -> AgentState:
    assert state.rendered_docx_path is not None
    output_path = f"{settings.DOCUMENT_STORAGE_PATH}/{state.report_id}/rendered.pdf"
    pdf_path = await convert_docx_to_pdf(state.rendered_docx_path, output_path)
    return state.model_copy(update={"rendered_pdf_path": pdf_path})
