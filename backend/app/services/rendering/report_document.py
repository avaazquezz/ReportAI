"""A report's document from its fields: the tenant's active template filled in, photos included,
converted to PDF. The pipeline, the panel's edits and its previews all render through here."""

import asyncio
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document_template import DocumentTemplate
from app.models.report_attachment import ReportAttachment
from app.services.agent.summary import format_value
from app.services.agent.tools.extraction_schema import TABLE, extractable_fields, image_fields
from app.services.jobs.errors import PermanentJobError
from app.services.rendering.docx_render import fill_template
from app.services.rendering.gotenberg_client import convert_docx_to_pdf


class MissingTemplateError(PermanentJobError):
    """The document type has no active template: no retry will render it until someone uploads one."""


async def _active_template_path(document_type_id: object) -> str:
    async with AsyncSessionLocal() as session:
        path = await session.scalar(
            select(DocumentTemplate.file_path)
            .where(DocumentTemplate.document_type_id == document_type_id, DocumentTemplate.is_active.is_(True))
            .limit(1)
        )
    if path is None:
        raise MissingTemplateError(f"No active template for document_type {document_type_id}")
    return path


async def _photo_paths(report_id: object) -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(ReportAttachment.path)
            .where(ReportAttachment.report_id == report_id)
            .order_by(ReportAttachment.created_at)
        )
        return list(rows)


def _readable(language: str, spec: dict[str, Any], value: Any) -> Any:
    """A date or a yes/no as a person writes it in the document's language, not as JSON."""
    if value is None:
        return None
    kind = spec.get("type")
    if kind in ("date", "bool"):
        return format_value(language, spec, value)
    if kind == TABLE:
        columns = spec.get("columns") or {}
        return [
            {**row, **{name: _readable(language, column, row.get(name)) for name, column in columns.items()}}
            for row in value
        ]
    return value


def template_values(field_schema: dict[str, Any], fields: dict[str, Any], language: str) -> dict[str, Any]:
    """What the template sees. A list or table nobody mentioned is null, and a template looping
    over it would crash: it gets an empty list instead."""
    values = dict(fields)
    for name, spec in extractable_fields(field_schema).items():
        if str(spec.get("type", "")).startswith("list[") and fields.get(name) is None:
            values[name] = []
        elif name in fields:
            values[name] = _readable(language, spec, fields[name])
    return values


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


async def fill_report_docx(
    *,
    report_id: object,
    document_type_id: object,
    field_schema: dict[str, Any],
    fields: dict[str, Any],
    language: str,
    output_path: str,
) -> str:
    template_path = await _active_template_path(document_type_id)
    photos = assign_photos(field_schema, await _photo_paths(report_id)) if image_fields(field_schema) else {}
    return await asyncio.to_thread(
        fill_template, template_path, template_values(field_schema, fields, language), output_path, photos
    )


async def render_report_pdf(
    *,
    report_id: object,
    document_type_id: object,
    field_schema: dict[str, Any],
    fields: dict[str, Any],
    language: str,
    folder: str,
) -> str:
    """Writes rendered.docx and rendered.pdf into `folder` and returns the PDF's path."""
    docx_path = await fill_report_docx(
        report_id=report_id,
        document_type_id=document_type_id,
        field_schema=field_schema,
        fields=fields,
        language=language,
        output_path=f"{folder}/rendered.docx",
    )
    return await convert_docx_to_pdf(docx_path, f"{folder}/rendered.pdf")
