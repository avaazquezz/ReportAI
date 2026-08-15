import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_type import DocumentType
from app.models.report import Report
from app.repositories.base import BaseRepository

PENDING_STATUSES = ("awaiting_doctype_selection", "awaiting_approval")


class ReportRepository(BaseRepository[Report]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Report, db)

    async def find_pending_for_sender(
        self, *, tenant_id: uuid.UUID, requester_identifier: str
    ) -> Report | None:
        query = (
            select(Report)
            .where(
                Report.tenant_id == tenant_id,
                Report.requester_identifier == requester_identifier,
                Report.status.in_(PENDING_STATUSES),
            )
            .order_by(Report.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def claim_for_resume(self, report_id: uuid.UUID) -> bool:
        """Atomically flip a paused report back to 'pending' (commits). Returns True if
        this call won the claim — the loser of a concurrent duplicate reply must not
        schedule a second resume of the same thread."""
        result = await self.db.execute(
            update(Report)
            .where(Report.id == report_id, Report.status.in_(PENDING_STATUSES))
            .values(status="pending")
            .returning(Report.id)
        )
        claimed = result.scalar_one_or_none() is not None
        await self.db.commit()
        return claimed

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
        self, *, tenant_id: uuid.UUID, skip: int = 0, limit: int = 100, status: str | None = None
    ) -> list[tuple[Report, str | None]]:
        query = (
            select(Report, DocumentType.name)
            .outerjoin(DocumentType, Report.document_type_id == DocumentType.id)
            .where(Report.tenant_id == tenant_id)
        )
        if status is not None:
            query = query.where(Report.status == status)
        query = query.order_by(Report.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def count_scoped(self, *, tenant_id: uuid.UUID, status: str | None = None) -> int:
        query = select(func.count()).select_from(Report).where(Report.tenant_id == tenant_id)
        if status is not None:
            query = query.where(Report.status == status)
        result = await self.db.execute(query)
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
