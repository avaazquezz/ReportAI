"""The landing's live demo: an anonymous visitor dictates (or types) a short site visit, watches the
real pipeline fill a report, and opens its PDF preview.

The report is made in the live demo's own company (PUBLIC_DEMO_USER_EMAIL's) through the app's own
channel, so the graph stops at awaiting_approval and nothing is sent to anyone: nobody approves it
and the worker deletes it, recording included, once it is PUBLIC_DEMO_TTL old. That company is never
the one-click demo's (DEMO_USER_EMAIL), which anyone can sign into: a visitor's recording is seen by
that visitor only. Every try costs AI, so a few per visitor, a ceiling for everyone and a budget of
its own, per day. Switched off, every route here is a 404 like one that doesn't exist."""

import ipaddress
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.capture import CaptureResponse
from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    ConflictException,
    PlanLimitException,
    RateLimitException,
    ResourceNotFoundException,
)
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.execution_log_repository import ExecutionLogRepository
from app.repositories.report_repository import FINISHED_STATUSES
from app.services import audit, plans
from app.services.agent.ingestion import create_report_with_job
from app.services.agent.tools.extraction_schema import missing_required_fields
from app.services.channels.web import WEB, store_voice_note, web_connection
from app.services.data_lifecycle import PUBLIC_DEMO_TTL, is_public_demo_report
from app.services.i18n import t
from app.services.rendering.report_document import MissingTemplateError, render_report_pdf

MAX_TEXT_CHARS = 2000
MAX_AUDIO_BYTES = 3 * 1024 * 1024  # a couple of minutes of speech: a short visit, not a meeting
# What a route that doesn't exist answers, so a switched-off demo can't be told from no demo.
_NOT_FOUND = "Not Found"
_READY = ("awaiting_approval", *FINISHED_STATUSES)
_FAILED = ("failed", "cancelled")
# Rendered once into the report's own folder, which the purge deletes with the report.
_PREVIEW = "demo-preview.pdf"

Locale = Literal["es", "en"]


def _visitor(request: Request) -> str:
    """Whom the per-visitor limits count: the address, or an IPv6 address's /64, which one home or
    one server gets whole (otherwise changing its last bits would buy more tries)."""
    ip = audit.client_ip(request)
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:  # no address to read ("unknown"): those all share one count
        return ip
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return ip


async def _within_budget(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """The demo's own AI budget for the UTC day, on top of the count of tries: a long recording
    costs more than the average one. Said to the visitor as the demo being full."""
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    spent = await ExecutionLogRepository(db).total_cost_since(midnight, tenant_id=tenant_id)
    if spent >= settings.PUBLIC_DEMO_DAILY_SPEND_USD:
        until_tomorrow = midnight + timedelta(days=1) - datetime.now(UTC)
        raise RateLimitException(max(int(until_tomorrow.total_seconds()), 1), rate_limit.DEMO_FULL)


def _require_demo() -> None:
    if not (settings.PUBLIC_DEMO_ENABLED and settings.PUBLIC_DEMO_USER_EMAIL and settings.PUBLIC_DEMO_DOCUMENT_TYPE_ES):
        raise ResourceNotFoundException(_NOT_FOUND)


router = APIRouter(prefix="/demo", tags=["public-demo"], dependencies=[Depends(_require_demo)])


class DemoReport(BaseModel):
    """The report as the visitor would review it. No ids, prompts, company or people in it: the
    visitor is anonymous and the company is ours."""

    status: Literal["processing", "ready", "failed"]
    document_type: str
    transcript: str | None
    fields: dict[str, Any] | None
    evidence: dict[str, Any] | None
    field_schema: dict[str, Any] | None
    missing: list[str]


def _unprocessable(field: str, message: str) -> RequestValidationError:
    """A 422 shaped like FastAPI's own (an over-long text, an unknown locale): the page reads one
    kind of input error."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": message, "input": None}])


async def _demo_account(db: AsyncSession) -> TenantUser:
    """The account whose company the demo works in. Missing, or in the one-click demo's company
    (which anyone can sign into), it is a broken deployment rather than anything a visitor did, so
    it fails loud."""
    account = await db.scalar(select(TenantUser).where(TenantUser.email == settings.PUBLIC_DEMO_USER_EMAIL))
    if account is None or account.tenant_id is None:
        raise RuntimeError("PUBLIC_DEMO_ENABLED is on but PUBLIC_DEMO_USER_EMAIL is not the account of a company")
    if settings.DEMO_USER_EMAIL:
        open_demo = await db.scalar(select(TenantUser.tenant_id).where(TenantUser.email == settings.DEMO_USER_EMAIL))
        if open_demo == account.tenant_id:
            raise RuntimeError("The live demo's company is the one-click demo's: visitors would see each other's recordings")
    return account


async def _document_type(db: AsyncSession, account: TenantUser, locale: Locale) -> DocumentType:
    configured = settings.PUBLIC_DEMO_DOCUMENT_TYPE_ES
    if locale == "en" and settings.PUBLIC_DEMO_DOCUMENT_TYPE_EN:
        configured = settings.PUBLIC_DEMO_DOCUMENT_TYPE_EN
    document_type = await db.get(DocumentType, uuid.UUID(configured))
    if document_type is None or document_type.tenant_id != account.tenant_id or not document_type.is_active:
        raise RuntimeError(f"The live demo's {locale} document type is not an active type of the demo company")
    return document_type


async def _visible_report(db: AsyncSession, report_id: uuid.UUID) -> tuple[Report, DocumentType | None]:
    """A report a visitor may see: the live demo's, in the demo company, under a day old. Anything
    else is a 404, whoever's it is."""
    account = await _demo_account(db)
    row = (
        await db.execute(
            select(Report, DocumentType)
            .outerjoin(DocumentType, DocumentType.id == Report.document_type_id)
            .where(
                Report.id == report_id,
                Report.tenant_id == account.tenant_id,
                is_public_demo_report(),
                Report.created_at > datetime.now(UTC) - PUBLIC_DEMO_TTL,
            )
        )
    ).first()
    if row is None:
        raise ResourceNotFoundException()
    report, document_type = row
    return report, document_type


def _status(report: Report) -> Literal["processing", "ready", "failed"]:
    if report.status in _READY:
        return "ready"
    if report.status in _FAILED:
        return "failed"
    return "processing"


@router.post("/capture", status_code=202)
async def capture_demo_report(
    request: Request,
    text: Annotated[str | None, Form(max_length=MAX_TEXT_CHARS)] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    locale: Annotated[Locale, Form()] = "es",
    db: AsyncSession = Depends(get_db),
) -> CaptureResponse:
    """Starts a demo report from a voice note and/or a typed note. A try is counted only once it
    is accepted, and simultaneous tries are counted one after another (rate_limit.claim), so a
    burst gets the same tries as a visitor clicking one at a time."""
    visitor = _visitor(request)
    # A first look without the lock, so most refused tries stop before anything is stored.
    await rate_limit.demo_capture_by_ip.check(db, visitor)
    await rate_limit.demo_capture_total.check(db, rate_limit.DEMO_TOTAL_KEY)

    text = (text or "").strip() or None
    if audio is None and text is None:
        raise _unprocessable("audio", "Record a voice note or type the visit")
    if audio is not None:
        if len(await audio.read(MAX_AUDIO_BYTES + 1)) > MAX_AUDIO_BYTES:
            raise _unprocessable("audio", f"The recording is over the {MAX_AUDIO_BYTES // (1024 * 1024)} MB limit")
        await audio.seek(0)  # store_voice_note reads it again

    account = await _demo_account(db)
    document_type = await _document_type(db, account, locale)
    tenant = await db.get(Tenant, account.tenant_id)
    # The same gates as the app's capture: the platform's daily spend cap, AI and voice set up.
    if refusal := await plans.message_refusal(db, tenant, voice=audio is not None):
        raise PlanLimitException(t(locale, refusal))
    assert tenant is not None  # message_refusal refuses a missing company
    if refusal := await plans.new_report_refusal(db, tenant):
        raise PlanLimitException(t(locale, refusal))
    await _within_budget(db, tenant.id)

    # An unsupported recording is refused here, before the try is counted.
    media_reference = await store_voice_note(audio) if audio is not None else None
    try:
        await rate_limit.claim(
            db,
            "demo_capture",
            (rate_limit.demo_capture_by_ip, visitor),
            (rate_limit.demo_capture_total, rate_limit.DEMO_TOTAL_KEY),
        )
    except RateLimitException:
        if media_reference is not None:  # a refused try's recording is not kept
            Path(media_reference).unlink(missing_ok=True)
        raise

    report = await create_report_with_job(
        db,
        await web_connection(db, tenant.id),
        sender_id=str(account.id),
        channel_type=WEB,
        text=text,
        media_reference=media_reference,
        sender_label=account.full_name,
        meta={"public_demo": True, "locale": locale},
        requester_user_id=account.id,
        document_type_id=document_type.id,
    )
    if report is None:  # a new id on the app's channel, which has no one-in-flight rule
        raise RuntimeError("A new live-demo report collided with an existing one")
    # The app's own captures learn it on extraction; the page shows the type from the start.
    report.document_type_id = document_type.id
    return CaptureResponse(id=report.id, status=report.status)


@router.get("/reports/{report_id}")
async def get_demo_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> DemoReport:
    """What the page polls: "ready" once the report waits for approval, with what was understood
    and the required fields it still lacks."""
    report, document_type = await _visible_report(db, report_id)
    schema = document_type.field_schema if document_type is not None else None
    fields = report.extracted_fields
    return DemoReport(
        status=_status(report),
        document_type=document_type.name if document_type is not None else "",
        transcript=report.source_text,
        fields=fields,
        evidence=report.evidence,
        field_schema=schema,
        missing=missing_required_fields(schema, fields) if schema is not None and fields is not None else [],
    )


@router.get("/reports/{report_id}/pdf")
async def demo_report_pdf(report_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """The PDF the report would make; nothing is sent. It is rendered on the first ask and kept in
    the report's own folder, which the purge deletes with the report: a demo report never changes
    once extracted, and a render is a trip to the Gotenberg the paying companies share. Renders,
    not reads, are counted per visitor."""
    report, document_type = await _visible_report(db, report_id)
    if report.extracted_fields is None or document_type is None:
        raise ConflictException("Nothing has been extracted from this report yet")
    preview = Path(settings.DOCUMENT_STORAGE_PATH) / str(report.id) / _PREVIEW
    if not preview.exists():
        await rate_limit.claim(db, "demo_pdf", (rate_limit.demo_pdf_by_ip, _visitor(request)))
        preview.parent.mkdir(parents=True, exist_ok=True)
        # Rendered beside its final place, then moved in whole: two first asks at once can't
        # leave half a file behind.
        with tempfile.TemporaryDirectory(dir=preview.parent) as folder:
            try:
                pdf_path = await render_report_pdf(
                    report_id=report.id,
                    document_type_id=document_type.id,
                    field_schema=document_type.field_schema,
                    fields=report.extracted_fields,
                    language=(report.channel_meta or {}).get("locale", "es"),
                    folder=folder,
                )
            except MissingTemplateError as exc:
                raise ConflictException("This document type has no active template") from exc
            os.replace(pdf_path, preview)
    return Response(content=preview.read_bytes(), media_type="application/pdf")
