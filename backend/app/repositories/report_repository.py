import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
