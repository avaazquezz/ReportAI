import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_log import ExecutionLog


class CostSummary(TypedDict):
    total_cost_usd: float
    avg_latency_ms: float | None


class ExecutionLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(self, *, tenant_id: uuid.UUID, since: datetime) -> CostSummary:
        query = select(
            func.coalesce(func.sum(ExecutionLog.cost_usd), 0),
            func.avg(ExecutionLog.latency_ms),
        ).where(ExecutionLog.tenant_id == tenant_id, ExecutionLog.created_at >= since)
        result = await self.db.execute(query)
        total_cost, avg_latency = result.one()
        return {
            "total_cost_usd": float(total_cost),
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
        }

    async def total_cost_since(self, since: datetime) -> float:
        """Platform-wide (no tenant filter) — feeds the global daily spend cap.
        ponytail: seq scan, fine at demo scale; index created_at if it ever hurts."""
        query = select(func.coalesce(func.sum(ExecutionLog.cost_usd), 0)).where(
            ExecutionLog.created_at >= since
        )
        result = await self.db.execute(query)
        return float(result.scalar_one() or 0)

    async def daily_cost_series(
        self, *, tenant_id: uuid.UUID, since: datetime
    ) -> list[tuple[str, float]]:
        day = func.date_trunc("day", ExecutionLog.created_at)
        query = (
            select(day, func.coalesce(func.sum(ExecutionLog.cost_usd), 0))
            .where(ExecutionLog.tenant_id == tenant_id, ExecutionLog.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        result = await self.db.execute(query)
        return [(row[0].date().isoformat(), float(row[1])) for row in result.all()]
