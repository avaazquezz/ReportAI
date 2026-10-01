import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Select, Text, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType
from app.models.report import Report
from app.repositories.base import BaseRepository

# Waiting on a person, not on the worker.
PENDING_STATUSES = ("awaiting_doctype_selection", "awaiting_details", "awaiting_approval")
# A sender has at most one of these (see uq_reports_one_active_per_sender).
ACTIVE_STATUSES = ("pending", *PENDING_STATUSES)
# The PDF exists. "delivery_failed" means none of its copies arrived (a resend can still fix that).
FINISHED_STATUSES = ("delivered", "delivery_failed")
TERMINAL_STATUSES = (*FINISHED_STATUSES, "failed", "cancelled")

_Query = TypeVar("_Query", bound=Select[*tuple[Any, ...]])


@dataclass(frozen=True)
class ReportFilters:
    """The history's filters. `created_to` is exclusive; the panel sends day boundaries in the
    viewer's own timezone, so no date is shifted by a UTC conversion here."""

    status: str | None = None
    document_type_id: uuid.UUID | None = None
    channel: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    q: str | None = None

    def apply(self, query: _Query) -> _Query:
        if self.status:
            query = query.where(Report.status == self.status)
        if self.document_type_id:
            query = query.where(Report.document_type_id == self.document_type_id)
        if self.channel:
            query = query.where(Report.requester_channel == self.channel)
        if self.created_from:
            query = query.where(Report.created_at >= self.created_from)
        if self.created_to:
            query = query.where(Report.created_at < self.created_to)
        if self.q and self.q.strip():
            # Who sent it, what they said, or anything in the fields ("García", an order number...).
            pattern = "%" + re.sub(r"([\\%_])", r"\\\1", self.q.strip()) + "%"
            query = query.where(
                or_(
                    Report.requester_identifier.ilike(pattern),
                    Report.source_text.ilike(pattern),
                    cast(Report.extracted_fields, Text).ilike(pattern),
                )
            )
        return query


class ReportRepository(BaseRepository[Report]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Report, db)

    async def find_active_for_sender(
        self, *, tenant_id: uuid.UUID, channel: str, identifier: str
    ) -> Report | None:
        query = select(Report).where(
            Report.tenant_id == tenant_id,
            Report.requester_channel == channel,
            Report.requester_identifier == identifier,
            Report.status.in_(ACTIVE_STATUSES),
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def count_recent_for_sender(
        self, *, tenant_id: uuid.UUID, requester_identifier: str, since: datetime
    ) -> int:
        query = (
            select(func.count())
            .select_from(Report)
            .where(
                Report.tenant_id == tenant_id,
                Report.requester_identifier == requester_identifier,
                Report.created_at >= since,
            )
        )
        result = await self.db.execute(query)
        return int(result.scalar_one())

    async def claim_for_resume(self, report_id: uuid.UUID) -> bool:
        """Atomically flip a paused report back to 'pending'. Returns True if this call won the
        claim — the loser of a concurrent duplicate reply must not enqueue a second resume.
        Does not commit: the caller commits it together with the resume job."""
        result = await self.db.execute(
            update(Report)
            .where(Report.id == report_id, Report.status.in_(PENDING_STATUSES))
            .values(status="pending")
            .returning(Report.id)
        )
        return result.scalar_one_or_none() is not None

    async def get_with_document_type_name(
        self, report_id: uuid.UUID
    ) -> tuple[Report, str | None] | None:
        query = (
            select(Report, DocumentType.name)
            .outerjoin(DocumentType, Report.document_type_id == DocumentType.id)
            .where(Report.id == report_id)
        )
        result = await self.db.execute(query)
        row = result.first()
        return None if row is None else (row[0], row[1])

    async def list_with_document_type_name(
        self, *, tenant_id: uuid.UUID, filters: ReportFilters, skip: int = 0, limit: int = 100
    ) -> list[tuple[Report, str | None]]:
        query = (
            select(Report, DocumentType.name)
            .outerjoin(DocumentType, Report.document_type_id == DocumentType.id)
            .where(Report.tenant_id == tenant_id)
        )
        query = filters.apply(query).order_by(Report.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def count_scoped(self, *, tenant_id: uuid.UUID, filters: ReportFilters) -> int:
        query = select(func.count()).select_from(Report).where(Report.tenant_id == tenant_id)
        result = await self.db.execute(filters.apply(query))
        return int(result.scalar_one())

    async def count_by_status(self, *, tenant_id: uuid.UUID, since: datetime) -> dict[str, int]:
        """Report-outcome counts come from `reports.status`, not `execution_logs` — a
        report has one row here but many in execution_logs (one per pipeline node)."""
        query = (
            select(Report.status, func.count())
            .where(Report.tenant_id == tenant_id, Report.created_at >= since)
            .group_by(Report.status)
        )
        result = await self.db.execute(query)
        return {status: count for status, count in result.all()}
