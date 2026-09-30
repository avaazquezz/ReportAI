import uuid
from typing import Any

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models.report import Report


async def save_report(report_id: uuid.UUID, **values: Any) -> None:
    """Writes progress onto the report row as the pipeline goes, so the panel can show what the
    pipeline knows without reading a LangGraph checkpoint."""
    async with AsyncSessionLocal() as session:
        await session.execute(update(Report).where(Report.id == report_id).values(**values))
        await session.commit()
