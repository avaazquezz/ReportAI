import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.scoping import require_tenant_id
from app.models.tenant_user import TenantUser
from app.repositories.execution_log_repository import ExecutionLogRepository
from app.repositories.report_repository import ReportRepository
from app.schemas.usage import DailyCostPoint, UsageSummaryResponse

router = APIRouter(prefix="/usage", tags=["admin:usage"])


async def build_usage_summary(
    db: AsyncSession, *, tenant_id: uuid.UUID, days: int
) -> UsageSummaryResponse:
    """Shared by this tenant-admin endpoint and the super-admin per-tenant drill-in in
    admin/tenants.py — same aggregation, only the tenant_id source differs."""
    since = datetime.now(UTC) - timedelta(days=days)
    execution_log_repo = ExecutionLogRepository(db)
    report_repo = ReportRepository(db)

    cost_summary = await execution_log_repo.summary(tenant_id=tenant_id, since=since)
    daily_cost = await execution_log_repo.daily_cost_series(tenant_id=tenant_id, since=since)
    reports_by_status = await report_repo.count_by_status(tenant_id=tenant_id, since=since)

    return UsageSummaryResponse(
        total_cost_usd=cost_summary["total_cost_usd"],
        total_reports=sum(reports_by_status.values()),
        reports_by_status=reports_by_status,
        avg_latency_ms=cost_summary["avg_latency_ms"],
        daily_cost=[DailyCostPoint(date=date, cost_usd=cost) for date, cost in daily_cost],
    )


@router.get("/summary")
async def get_usage_summary(
    days: int = 30,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    tenant_id = require_tenant_id(current_user)
    return await build_usage_summary(db, tenant_id=tenant_id, days=days)
