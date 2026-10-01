"""The panel's first page: what is waiting on someone, what went wrong, and — for an admin — the
steps left before the company's first report."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_tenant_member
from app.core.scoping import require_tenant_id
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.tenant_user import TenantUser
from app.repositories.report_repository import PENDING_STATUSES
from app.services import instance_settings
from app.services.sender_invites import sender_labels

router = APIRouter(prefix="/dashboard", tags=["admin:dashboard"])

_RECENT = timedelta(days=7)
_LISTED = 5


class DashboardReport(BaseModel):
    id: uuid.UUID
    status: str
    document_type_name: str | None
    requester: str  # who sent it: the name they were invited as, or their id
    error_detail: str | None
    created_at: datetime


class DashboardCounts(BaseModel):
    waiting: int  # paused on a person: a type to pick, details, an approval
    processing: int
    delivered_recently: int
    failed_recently: int
    failed_copies_recently: int  # delivered reports with a copy that did not arrive


class Checklist(BaseModel):
    ai: bool
    transcription: bool
    email: bool
    channel: bool
    senders: bool
    document_type: bool
    first_report: bool


class DashboardResponse(BaseModel):
    counts: DashboardCounts
    waiting: list[DashboardReport]
    failed: list[DashboardReport]
    checklist: Checklist | None  # admins only


async def _listed(db: AsyncSession, tenant_id: uuid.UUID, *conditions: object) -> list[DashboardReport]:
    rows = (
        await db.execute(
            select(Report, DocumentType.name)
            .outerjoin(DocumentType, Report.document_type_id == DocumentType.id)
            .where(Report.tenant_id == tenant_id, *conditions)  # type: ignore[arg-type]
            .order_by(Report.created_at.desc())
            .limit(_LISTED)
        )
    ).all()
    connections = list({r.channel_connection_id for r, _ in rows if r.channel_connection_id})
    labels = await sender_labels(db, connections)
    return [
        DashboardReport(
            id=report.id,
            status=report.status,
            document_type_name=type_name,
            requester=labels.get(report.channel_connection_id, {}).get(report.requester_identifier)  # type: ignore[arg-type]
            or report.requester_identifier,
            error_detail=report.error_detail,
            created_at=report.created_at,
        )
        for report, type_name in rows
    ]


async def _checklist(db: AsyncSession, tenant_id: uuid.UUID) -> Checklist:
    stored = await instance_settings.load(db)

    async def any_of(*conditions: object) -> bool:
        return bool(await db.scalar(select(exists().where(*conditions))))  # type: ignore[arg-type]

    channel = (ChannelConnection.tenant_id == tenant_id, ChannelConnection.is_active.is_(True))
    return Checklist(
        ai=instance_settings.ai_from(stored).configured,
        transcription=instance_settings.transcription_from(stored).configured,
        email=instance_settings.smtp_from(stored).configured,
        channel=await any_of(*channel),
        senders=settings.ALLOW_ANY_SENDER or await any_of(*channel, func.cardinality(ChannelConnection.allowed_senders) > 0),
        document_type=await any_of(
            DocumentTemplate.tenant_id == tenant_id,
            DocumentTemplate.is_active.is_(True),
            DocumentTemplate.document_type_id.in_(
                select(DocumentType.id).where(DocumentType.tenant_id == tenant_id, DocumentType.is_active.is_(True))
            ),
        ),
        first_report=await any_of(Report.tenant_id == tenant_id, Report.status == "delivered"),
    )


@router.get("")
async def get_dashboard(
    current_user: TenantUser = Depends(require_tenant_member), db: AsyncSession = Depends(get_db)
) -> DashboardResponse:
    tenant_id = require_tenant_id(current_user)
    since = datetime.now(UTC) - _RECENT
    by_status = dict(
        (
            await db.execute(
                select(Report.status, func.count()).where(Report.tenant_id == tenant_id).group_by(Report.status)
            )
        ).all()
    )
    recent = dict(
        (
            await db.execute(
                select(Report.status, func.count())
                .where(Report.tenant_id == tenant_id, Report.created_at >= since)
                .group_by(Report.status)
            )
        ).all()
    )
    failed_copies = await db.scalar(
        select(func.count(func.distinct(Delivery.report_id)))
        .join(Report, Report.id == Delivery.report_id)
        .where(Report.tenant_id == tenant_id, Report.status == "delivered", Delivery.status == "failed", Delivery.updated_at >= since)
    )
    failed_statuses = ("failed", "delivery_failed")
    return DashboardResponse(
        counts=DashboardCounts(
            waiting=sum(by_status.get(s, 0) for s in PENDING_STATUSES),
            processing=by_status.get("pending", 0),
            delivered_recently=recent.get("delivered", 0),
            failed_recently=sum(recent.get(s, 0) for s in failed_statuses),
            failed_copies_recently=failed_copies or 0,
        ),
        waiting=await _listed(db, tenant_id, Report.status.in_(PENDING_STATUSES)),
        failed=await _listed(db, tenant_id, Report.status.in_(failed_statuses), Report.created_at >= since),
        checklist=await _checklist(db, tenant_id) if current_user.role == "tenant_admin" else None,
    )
