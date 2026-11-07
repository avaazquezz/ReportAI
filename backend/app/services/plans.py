"""What each company may use: its plan, the plan's period, and the checks that refuse a message
when the plan says no. The catalog lives here, in code, so a plan is versioned and tested with
the rules that read it; billing (later) only maps a subscription onto `tenants.plan*`.

Self-host (SINGLE_TENANT) has no plans: the company owns the server and pays its own AI.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.report import Report
from app.models.tenant import Tenant
from app.repositories.execution_log_repository import ExecutionLogRepository
from app.services import instance_settings

TRIAL_DAYS = 14
STATUSES = ("trialing", "active", "past_due", "canceled")


@dataclass(frozen=True)
class Plan:
    key: str
    monthly_reports: int | None  # None: no quota
    daily_spend_usd: float | None  # None: only the platform-wide breaker applies


# Report quotas are first guesses to validate with pilots. The spend caps are a wallet guard
# (an extraction costs about 0.04 USD), set far above normal use for each quota.
PLANS: dict[str, Plan] = {
    plan.key: plan
    for plan in (
        Plan("unlimited", None, None),  # tenants from before plans existed, the demo, internal
        Plan("trial", 30, 2.0),
        Plan("starter", 50, 5.0),
        Plan("pro", 250, 15.0),
        Plan("business", 1000, 50.0),
    )
}


def plan_of(tenant: Tenant) -> Plan:
    return PLANS[tenant.plan]


def add_month(moment: datetime) -> datetime:
    """Same day next month, or that month's last day (31 Jan → 28/29 Feb)."""
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    return moment.replace(year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1]))


def start_plan(tenant: Tenant, key: str, status: str, *, now: datetime | None = None) -> None:
    """Puts a company on a plan from now: a trial runs TRIAL_DAYS, a paid plan a month."""
    if key not in PLANS:
        raise ValueError(f"Unknown plan {key!r}")
    if status not in STATUSES:
        raise ValueError(f"Unknown plan status {status!r}")
    now = now or datetime.now(UTC)
    tenant.plan, tenant.plan_status = key, status
    tenant.plan_period_start = now
    tenant.plan_period_end = now + timedelta(days=TRIAL_DAYS) if status == "trialing" else add_month(now)


async def reports_this_period(db: AsyncSession, tenant: Tenant) -> int:
    """Reports the company started this period; failed ones are on us, not on its quota."""
    query = select(func.count()).where(Report.tenant_id == tenant.id, Report.status != "failed")
    if tenant.plan_period_start is not None:
        query = query.where(Report.created_at >= tenant.plan_period_start)
    return int((await db.execute(query)).scalar_one())


def _midnight_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def message_refusal(db: AsyncSession, tenant: Tenant | None, *, voice: bool) -> str | None:
    """Why this company can't have anything processed right now, as an i18n key, or None.
    Checked for every message, replies to a paused report included: they cost AI too."""
    if tenant is None or not tenant.is_active:
        return "tenant_suspended"
    if settings.DAILY_SPEND_CAP_USD > 0:  # platform-wide breaker, whatever the plan
        spent = await ExecutionLogRepository(db).total_cost_since(_midnight_utc())
        if spent >= settings.DAILY_SPEND_CAP_USD:
            return "spend_capped"
    if not settings.SINGLE_TENANT:
        if tenant.plan_status == "canceled":
            return "plan_inactive"
        if tenant.plan_status == "trialing" and tenant.plan_period_end and tenant.plan_period_end <= datetime.now(UTC):
            return "trial_ended"
        cap = plan_of(tenant).daily_spend_usd
        if cap is not None:
            spent = await ExecutionLogRepository(db).total_cost_since(_midnight_utc(), tenant_id=tenant.id)
            if spent >= cap:
                return "spend_capped"
    if voice and not instance_settings.transcription_from(await instance_settings.load(db)).configured:
        return "voice_not_configured"
    return None


async def new_report_refusal(db: AsyncSession, tenant: Tenant) -> str | None:
    """On top of message_refusal, for a message that would start a new report."""
    if not instance_settings.ai_from(await instance_settings.load(db)).configured:
        return "not_configured"
    quota = None if settings.SINGLE_TENANT else plan_of(tenant).monthly_reports
    # ponytail: count-then-create, so two senders at once can overshoot the quota by one or two;
    # a per-tenant lock isn't worth it while say() makes network calls inside the transaction.
    if quota is not None and await reports_this_period(db, tenant) >= quota:
        return "quota_reached"
    return None


async def advance_periods(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Rolls an active plan whose month is over into the next one: the quota starts again.
    Trials don't roll (they end). Once billing exists, it moves the period instead."""
    now = now or datetime.now(UTC)
    tenants = (
        await db.scalars(
            select(Tenant).where(
                Tenant.plan_status.in_(("active", "past_due")),
                Tenant.plan_period_end.is_not(None),
                Tenant.plan_period_end <= now,
            )
        )
    ).all()
    for tenant in tenants:
        start, end = tenant.plan_period_start, tenant.plan_period_end
        while end is not None and end <= now:
            start, end = end, add_month(end)
        tenant.plan_period_start, tenant.plan_period_end = start, end
    return len(tenants)
