import csv
import io
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ConflictException, ResourceNotFoundException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.report_revision import ReportRevision
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.report_repository import (
    FINISHED_STATUSES,
    PENDING_STATUSES,
    ReportFilters,
    ReportRepository,
)
from app.schemas.common import PaginatedResponse
from app.schemas.report import (
    ApproveRequest,
    DeliveryResponse,
    EditFieldsRequest,
    PhotoResponse,
    RejectRequest,
    ReportDetailResponse,
    ReportResponse,
    ResendRequest,
    RevisionResponse,
    StepResponse,
)
from app.services.agent.ingestion import request_resume, say
from app.services.agent.summary import format_value
from app.services.agent.tools.extraction_schema import (
    extractable_fields,
    field_label,
    merge_edits,
    missing_required_fields,
)
from app.services.delivery.deliveries import attachment_name, local_day, request_resend
from app.services.i18n import t
from app.services.rendering.report_document import MissingTemplateError, render_report_pdf

router = APIRouter(prefix="/reports", tags=["admin:reports"])

_EXPORT_LIMIT = 10_000
# A cell that starts like a formula runs as one when the CSV is opened in a spreadsheet, and
# these values come from whatever someone said in a voice note.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _to_response(report: Report, document_type_name: str | None) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        tenant_id=report.tenant_id,
        document_type_id=report.document_type_id,
        document_type_name=document_type_name,
        status=report.status,
        requester_channel=report.requester_channel,
        requester_identifier=report.requester_identifier,
        error_detail=report.error_detail,
        download_url=f"/reports/{report.id}/download" if report.file_path else None,
        created_at=report.created_at,
        completed_at=report.completed_at,
    )


def _filters(
    status: str | None = None,
    document_type_id: uuid.UUID | None = None,
    channel: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> ReportFilters:
    return ReportFilters(
        status=status,
        document_type_id=document_type_id,
        channel=channel,
        created_from=created_from,
        created_to=created_to,
        q=q,
    )


async def _load(db: AsyncSession, report_id: uuid.UUID, user: TenantUser) -> Report:
    return await get_scoped_or_404(ReportRepository(db), report_id, tenant_id=require_tenant_id(user))


async def _document_type(db: AsyncSession, report: Report) -> DocumentType:
    document_type = await db.get(DocumentType, report.document_type_id) if report.document_type_id else None
    if document_type is None:
        raise ConflictException("This report has no document type")
    return document_type


async def _language(db: AsyncSession, report: Report) -> str:
    tenant = await db.get(Tenant, report.tenant_id)
    assert tenant is not None
    return tenant.language


def _apply_edits(
    document_type: DocumentType, current: dict[str, Any], edits: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = document_type.field_schema
    unknown = sorted(set(edits) - set(extractable_fields(schema)))
    if unknown:
        raise ValidationException(f"Unknown fields: {', '.join(unknown)}")
    try:
        return merge_edits(document_type.name, schema, current, edits)
    except ValidationError as exc:
        problems = [
            f"{field_label(str(error['loc'][0]), schema.get(str(error['loc'][0]), {}))}: {error['msg']}"
            for error in exc.errors()
        ]
        raise ValidationException("; ".join(problems)) from exc


def _require_complete(document_type: DocumentType, fields: dict[str, Any]) -> None:
    missing = missing_required_fields(document_type.field_schema, fields)
    if missing:
        labels = ", ".join(field_label(name, document_type.field_schema[name]) for name in missing)
        raise ValidationException(f"Required fields are missing: {labels}")


async def _detail(db: AsyncSession, report: Report) -> ReportDetailResponse:
    document_type = await db.get(DocumentType, report.document_type_id) if report.document_type_id else None
    deliveries = await db.scalars(
        select(Delivery).where(Delivery.report_id == report.id).order_by(Delivery.created_at, Delivery.kind)
    )
    steps = await db.scalars(
        select(ExecutionLog).where(ExecutionLog.report_id == report.id).order_by(ExecutionLog.created_at)
    )
    revisions = await db.execute(
        select(ReportRevision, TenantUser.full_name)
        .outerjoin(TenantUser, ReportRevision.user_id == TenantUser.id)
        .where(ReportRevision.report_id == report.id)
        .order_by(ReportRevision.created_at)
    )
    photos = await db.scalars(
        select(ReportAttachment).where(ReportAttachment.report_id == report.id).order_by(ReportAttachment.created_at)
    )
    return ReportDetailResponse(
        **_to_response(report, document_type.name if document_type else None).model_dump(),
        received_at=report.received_at,
        updated_at=report.updated_at,
        source_text=report.source_text,
        audio_url=f"/reports/{report.id}/audio" if report.audio_path else None,
        reject_reason=report.reject_reason,
        extracted_fields=report.extracted_fields,
        evidence=report.evidence,
        field_schema=document_type.field_schema if document_type else None,
        photos=[
            PhotoResponse(id=photo.id, url=f"/reports/{report.id}/photos/{photo.id}", caption=photo.caption)
            for photo in photos
        ],
        deliveries=[DeliveryResponse.model_validate(delivery) for delivery in deliveries],
        steps=[StepResponse.model_validate(step) for step in steps],
        revisions=[
            RevisionResponse(
                action=revision.action,
                user_name=user_name,
                changes=revision.changes,
                note=revision.note,
                created_at=revision.created_at,
            )
            for revision, user_name in revisions.all()
        ],
    )


async def _refreshed_detail(db: AsyncSession, report: Report) -> ReportDetailResponse:
    await db.flush()
    await db.refresh(report)
    return await _detail(db, report)


@router.get("")
async def list_reports(
    skip: int = 0,
    limit: int = Query(default=100, le=500),
    filters: ReportFilters = Depends(_filters),
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ReportResponse]:
    tenant_id = require_tenant_id(current_user)
    repo = ReportRepository(db)
    rows = await repo.list_with_document_type_name(tenant_id=tenant_id, filters=filters, skip=skip, limit=limit)
    total = await repo.count_scoped(tenant_id=tenant_id, filters=filters)
    return PaginatedResponse(
        items=[_to_response(report, name) for report, name in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


@router.get("/export.csv")
async def export_reports(
    filters: ReportFilters = Depends(_filters),
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The filtered history as a spreadsheet. Filtered to one document type, each field gets its
    own column; otherwise the fields go in one JSON column, since every type has different ones."""
    tenant_id = require_tenant_id(current_user)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    zone = ZoneInfo(tenant.timezone)
    rows = await ReportRepository(db).list_with_document_type_name(
        tenant_id=tenant_id, filters=filters, limit=_EXPORT_LIMIT
    )
    document_type = await db.get(DocumentType, filters.document_type_id) if filters.document_type_id else None
    columns = (
        extractable_fields(document_type.field_schema)
        if document_type is not None and document_type.tenant_id == tenant_id
        else None
    )

    out = io.StringIO()
    writer = csv.writer(out)
    header = ["id", "created_at", "status", "document_type", "channel", "requester", "completed_at", "error"]
    writer.writerow(header + ([field_label(name, spec) for name, spec in columns.items()] if columns else ["fields"]))
    for report, document_type_name in rows:
        fields = report.extracted_fields or {}
        row: list[object] = [
            report.id,
            report.created_at.astimezone(zone).strftime("%Y-%m-%d %H:%M"),
            report.status,
            document_type_name,
            report.requester_channel,
            report.requester_identifier,
            report.completed_at.astimezone(zone).strftime("%Y-%m-%d %H:%M") if report.completed_at else None,
            report.error_detail,
        ]
        if columns:
            row += [
                None if fields.get(name) is None else format_value(tenant.language, spec, fields[name])
                for name, spec in columns.items()
            ]
        else:
            row.append(json.dumps(fields, ensure_ascii=False) if fields else None)
        writer.writerow([_cell(value) for value in row])
    # The BOM makes Excel read the file as UTF-8 (accents, ñ) instead of the system code page.
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reports.csv"'},
    )


@router.get("/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    return await _detail(db, await _load(db, report_id, current_user))


@router.post("/{report_id}/approve", status_code=202)
async def approve_report(
    report_id: uuid.UUID,
    payload: ApproveRequest | None = None,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """Approve a paused report, with the reviewer's corrections if any — the same as the requester
    confirming on the channel, and the recovery path when the approval prompt never reached them.
    Required fields must be filled: an approval is a decision to send the document as it is."""
    report = await _load(db, report_id, current_user)
    if report.status != "awaiting_approval":
        raise ConflictException("Report is not awaiting approval")
    changes: dict[str, Any] = {}
    if report.document_type_id is not None:
        document_type = await _document_type(db, report)
        fields, changes = _apply_edits(document_type, report.extracted_fields or {}, (payload or ApproveRequest()).fields)
        _require_complete(document_type, fields)
    reply: dict[str, Any] = {"action": "confirm"}
    if changes:
        reply["fields"] = {name: change["to"] for name, change in changes.items()}
    if not await request_resume(db, report, reply):
        raise ConflictException("Report was already resumed")
    db.add(ReportRevision(report_id=report.id, user_id=current_user.id, action="approve", changes=changes or None))
    return await _refreshed_detail(db, report)


@router.post("/{report_id}/reject")
async def reject_report(
    report_id: uuid.UUID,
    payload: RejectRequest | None = None,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """End a paused report without generating it, and tell the requester why. Unblocks the sender:
    their next message would otherwise be captured as a reply to this report."""
    report = await _load(db, report_id, current_user)
    reason = ((payload.reason if payload else None) or "").strip() or None
    rejected = await db.execute(
        update(Report)
        .where(Report.id == report.id, Report.status.in_(PENDING_STATUSES))
        .values(
            status="failed",
            error_detail="Rejected by admin",
            reject_reason=reason,
            completed_at=datetime.now(UTC),
        )
        .returning(Report.id)
    )
    if rejected.first() is None:
        raise ConflictException("Report is not awaiting a reply")
    db.add(ReportRevision(report_id=report.id, user_id=current_user.id, action="reject", note=reason))
    await db.commit()

    connection = await db.get(ChannelConnection, report.channel_connection_id) if report.channel_connection_id else None
    tenant = await db.get(Tenant, report.tenant_id)
    if connection is not None and tenant is not None:
        text = t(tenant.language, "rejected_reason", reason=reason) if reason else t(tenant.language, "rejected")
        await say(connection, report.requester_identifier, text, meta=report.channel_meta)
    return await _refreshed_detail(db, report)


@router.patch("/{report_id}/fields")
async def edit_report_fields(
    report_id: uuid.UUID,
    payload: EditFieldsRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    """Correct a delivered report and regenerate its PDF (with no changes, it only regenerates:
    after a template update, say). Nothing is sent: resending is a separate decision."""
    report = await _load(db, report_id, current_user)
    if report.status not in FINISHED_STATUSES or not report.file_path:
        raise ConflictException("Only a delivered report can be edited; approve a paused one with its edits")
    document_type = await _document_type(db, report)
    fields, changes = _apply_edits(document_type, report.extracted_fields or {}, payload.fields)
    _require_complete(document_type, fields)
    try:
        pdf_path = await render_report_pdf(
            report_id=report.id,
            document_type_id=document_type.id,
            field_schema=document_type.field_schema,
            fields=fields,
            language=await _language(db, report),
            folder=str(Path(report.file_path).parent),
        )
    except MissingTemplateError as exc:
        raise ConflictException("This document type has no active template") from exc
    report.extracted_fields = fields
    report.file_path = pdf_path
    # A quote backs what the model extracted, not what a person typed over it.
    report.evidence = {name: quote for name, quote in (report.evidence or {}).items() if name not in changes}
    db.add(
        ReportRevision(
            report_id=report.id,
            user_id=current_user.id,
            action="edit" if changes else "rerender",
            changes=changes or None,
        )
    )
    return await _refreshed_detail(db, report)


@router.post("/{report_id}/preview")
async def preview_report(
    report_id: uuid.UUID,
    payload: EditFieldsRequest | None = None,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """The PDF as it would come out with these edits, without saving or sending anything."""
    report = await _load(db, report_id, current_user)
    if report.extracted_fields is None:
        raise ConflictException("Nothing has been extracted from this report yet")
    document_type = await _document_type(db, report)
    fields, _ = _apply_edits(document_type, report.extracted_fields, (payload or EditFieldsRequest()).fields)
    with tempfile.TemporaryDirectory() as folder:
        try:
            pdf_path = await render_report_pdf(
                report_id=report.id,
                document_type_id=document_type.id,
                field_schema=document_type.field_schema,
                fields=fields,
                language=await _language(db, report),
                folder=folder,
            )
        except MissingTemplateError as exc:
            raise ConflictException("This document type has no active template") from exc
        content = Path(pdf_path).read_bytes()
    return Response(content=content, media_type="application/pdf")


@router.post("/{report_id}/resend", status_code=202)
async def resend_report(
    report_id: uuid.UUID,
    payload: ResendRequest | None = None,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportDetailResponse:
    report = await _load(db, report_id, current_user)
    if report.status not in FINISHED_STATUSES or not report.file_path:
        raise ConflictException("Only a delivered report can be sent again")
    request = payload or ResendRequest()
    destinations = await request_resend(db, report.id, delivery_id=request.delivery_id, email=request.email)
    if not destinations:
        raise ConflictException("Nothing to resend")
    db.add(ReportRevision(report_id=report.id, user_id=current_user.id, action="resend", note=", ".join(destinations)))
    return await _refreshed_detail(db, report)


@router.get("/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    report = await _load(db, report_id, current_user)
    if not report.file_path:
        raise ResourceNotFoundException("No file available for this report")
    tenant = await db.get(Tenant, report.tenant_id)
    document_type = await db.get(DocumentType, report.document_type_id) if report.document_type_id else None
    assert tenant is not None
    name = attachment_name(
        document_type.name if document_type else t(tenant.language, "report"), local_day(report, tenant.timezone)
    )
    return FileResponse(report.file_path, filename=name, media_type="application/pdf")


@router.get("/{report_id}/audio")
async def report_audio(
    report_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    report = await _load(db, report_id, current_user)
    if not report.audio_path:
        raise ResourceNotFoundException("This report has no audio")
    return FileResponse(report.audio_path, media_type="audio/ogg")


@router.get("/{report_id}/photos/{photo_id}")
async def report_photo(
    report_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    report = await _load(db, report_id, current_user)
    photo = await db.get(ReportAttachment, photo_id)
    if photo is None or photo.report_id != report.id:
        raise ResourceNotFoundException()
    return FileResponse(photo.path, media_type="image/jpeg")
