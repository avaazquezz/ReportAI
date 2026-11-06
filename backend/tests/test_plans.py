"""Plans: a trial ends, a quota stops new reports (never a reply to one in progress), one
company's daily cap doesn't touch another's, and self-host has no plans at all."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.channel_connection import ChannelConnection
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import instance_settings, plans
from app.services.agent import ingestion
from app.services.agent.ingestion import ingest_message
from app.services.channels.base import IncomingMessage
from app.services.i18n import t


@pytest.fixture(autouse=True)
def _ai_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def configured(session: object = None) -> dict[str, str]:
        return {"extraction_api_key": "k", "transcription_api_key": "k"}

    monkeypatch.setattr(instance_settings, "load", configured)


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(ingestion, "get_channel_adapter", lambda _connection: mock)
    return mock


async def _company(db: AsyncSession, *, plan: str = "starter", status: str = "active") -> tuple[Tenant, ChannelConnection]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True, language="es")
    plans.start_plan(tenant, plan, status)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "t"},
        allowed_senders=[],
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    return tenant, connection


def _message(connection: ChannelConnection, sender: str = "42", text: str = "Visité la obra") -> IncomingMessage:
    return IncomingMessage(
        channel_type="telegram",
        channel_connection_id=connection.id,
        sender_id=sender,
        text=text,
        raw_payload={},
    )


async def _past_reports(db: AsyncSession, tenant: Tenant, n: int, *, status: str = "delivered") -> None:
    for i in range(n):
        db.add(
            Report(
                tenant_id=tenant.id,
                status=status,
                requester_channel="telegram",
                requester_identifier=f"old-{i}",
            )
        )
    await db.commit()


async def _spent(db: AsyncSession, tenant: Tenant, usd: float) -> None:
    db.add(ExecutionLog(tenant_id=tenant.id, step="extract", status="success", cost_usd=usd))
    await db.commit()


def _said(adapter: AsyncMock) -> str:
    return str(adapter.send_message.await_args.args[0].text)


def test_a_month_later_is_the_same_day_or_the_month_s_last_one() -> None:
    assert plans.add_month(datetime(2026, 1, 31, tzinfo=UTC)) == datetime(2026, 2, 28, tzinfo=UTC)
    assert plans.add_month(datetime(2028, 1, 31, tzinfo=UTC)) == datetime(2028, 2, 29, tzinfo=UTC)
    assert plans.add_month(datetime(2026, 12, 15, tzinfo=UTC)) == datetime(2027, 1, 15, tzinfo=UTC)


def test_a_trial_lasts_its_days_and_a_paid_plan_a_month() -> None:
    now = datetime(2026, 11, 6, 12, tzinfo=UTC)
    trial, paid = Tenant(name="a", slug="a"), Tenant(name="b", slug="b")

    plans.start_plan(trial, "trial", "trialing", now=now)
    plans.start_plan(paid, "pro", "active", now=now)

    assert trial.plan_period_end == now + timedelta(days=plans.TRIAL_DAYS)
    assert paid.plan_period_end == datetime(2026, 12, 6, 12, tzinfo=UTC)
    with pytest.raises(ValueError):
        plans.start_plan(paid, "platinum", "active")


async def test_at_quota_a_new_report_is_refused_and_nothing_is_created(db: AsyncSession, adapter: AsyncMock) -> None:
    tenant, connection = await _company(db, plan="starter")
    await _past_reports(db, tenant, plans.PLANS["starter"].monthly_reports or 0)

    result = await ingest_message(db=db, connection=connection, incoming=_message(connection))
    await db.commit()

    assert result.outcome == "rejected"
    assert _said(adapter) == t("es", "quota_reached")
    assert (await db.execute(select(Job))).scalars().all() == []


async def test_failed_reports_and_last_period_s_do_not_count(db: AsyncSession, adapter: AsyncMock) -> None:
    tenant, connection = await _company(db, plan="starter")
    quota = plans.PLANS["starter"].monthly_reports or 0
    await _past_reports(db, tenant, quota, status="failed")
    await _past_reports(db, tenant, quota - 1)
    assert tenant.plan_period_start is not None
    old = Report(tenant_id=tenant.id, status="delivered", requester_channel="telegram", requester_identifier="x")
    db.add(old)
    await db.flush()
    old.created_at = tenant.plan_period_start - timedelta(days=1)
    await db.commit()

    result = await ingest_message(db=db, connection=connection, incoming=_message(connection))

    assert result.outcome == "created"


async def test_at_quota_a_reply_to_a_paused_report_still_goes_through(db: AsyncSession, adapter: AsyncMock) -> None:
    tenant, connection = await _company(db, plan="starter")
    await _past_reports(db, tenant, plans.PLANS["starter"].monthly_reports or 0)
    db.add(
        Report(
            tenant_id=tenant.id,
            status="awaiting_details",
            requester_channel="telegram",
            requester_identifier="42",
            channel_connection_id=connection.id,
        )
    )
    await db.commit()

    result = await ingest_message(db=db, connection=connection, incoming=_message(connection, text="el viernes"))

    assert result.outcome == "resumed"


async def test_an_ended_trial_or_a_canceled_plan_refuses_every_message(db: AsyncSession, adapter: AsyncMock) -> None:
    trial, trial_bot = await _company(db, plan="trial", status="trialing")
    trial.plan_period_end = datetime.now(UTC) - timedelta(minutes=1)
    _, canceled_bot = await _company(db, plan="pro", status="canceled")
    await db.commit()

    assert (await ingest_message(db=db, connection=trial_bot, incoming=_message(trial_bot))).outcome == "rejected"
    assert _said(adapter) == t("es", "trial_ended")
    assert (await ingest_message(db=db, connection=canceled_bot, incoming=_message(canceled_bot))).outcome == "rejected"
    assert _said(adapter) == t("es", "plan_inactive")


async def test_one_company_s_daily_cap_does_not_stop_another(db: AsyncSession, adapter: AsyncMock) -> None:
    capped, capped_bot = await _company(db, plan="trial", status="trialing")
    _, other_bot = await _company(db, plan="trial", status="trialing")
    await _spent(db, capped, plans.PLANS["trial"].daily_spend_usd or 0)

    refused = await ingest_message(db=db, connection=capped_bot, incoming=_message(capped_bot))
    assert refused.outcome == "rejected" and _said(adapter) == t("es", "spend_capped")

    accepted = await ingest_message(db=db, connection=other_bot, incoming=_message(other_bot))
    assert accepted.outcome == "created"


async def test_the_platform_breaker_still_stops_everyone(
    db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DAILY_SPEND_CAP_USD", 1.0)
    _, unlimited_bot = await _company(db, plan="unlimited")
    other, _ = await _company(db, plan="unlimited")
    await _spent(db, other, 1.0)

    result = await ingest_message(db=db, connection=unlimited_bot, incoming=_message(unlimited_bot))

    assert result.outcome == "rejected" and _said(adapter) == t("es", "spend_capped")


async def test_self_host_has_no_plans(db: AsyncSession, adapter: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    tenant, connection = await _company(db, plan="trial", status="trialing")
    tenant.plan_period_end = datetime.now(UTC) - timedelta(days=30)
    await db.commit()
    await _past_reports(db, tenant, 1000)
    await _spent(db, tenant, 500.0)

    result = await ingest_message(db=db, connection=connection, incoming=_message(connection))

    assert result.outcome == "created"


async def test_an_active_plan_rolls_into_a_new_month_and_a_trial_does_not(db: AsyncSession) -> None:
    month_ago = datetime.now(UTC) - timedelta(days=31)
    paid, _ = await _company(db, plan="pro")
    trial, _ = await _company(db, plan="trial", status="trialing")
    plans.start_plan(paid, "pro", "active", now=month_ago)
    plans.start_plan(trial, "trial", "trialing", now=month_ago)
    await db.commit()

    assert await plans.advance_periods(db) == 1

    assert paid.plan_period_start is not None and paid.plan_period_end is not None
    assert paid.plan_period_start <= datetime.now(UTC) < paid.plan_period_end
    assert trial.plan_period_end is not None and trial.plan_period_end < datetime.now(UTC)


async def _admin(db: AsyncSession, tenant: Tenant) -> dict[str, str]:
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"admin-{uuid.uuid4().hex[:6]}@acme.test",
        hashed_password=hash_password("x"),
        full_name="Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(tenant.id), "ver": 0})
    return {"Authorization": f"Bearer {token}"}


async def test_the_company_sees_its_plan_and_usage(client: AsyncClient, db: AsyncSession) -> None:
    tenant, _ = await _company(db, plan="pro")
    await _past_reports(db, tenant, 3)
    await _past_reports(db, tenant, 2, status="failed")

    response = await client.get("/company/plan", headers=await _admin(db, tenant))

    assert response.status_code == 200
    body = response.json()
    assert (body["plan"], body["status"], body["reports_used"]) == ("pro", "active", 3)
    assert body["reports_limit"] == plans.PLANS["pro"].monthly_reports


async def test_the_template_assistant_is_refused_once_the_cap_is_hit(client: AsyncClient, db: AsyncSession) -> None:
    tenant, _ = await _company(db, plan="trial", status="trialing")
    doc_type = DocumentType(tenant_id=tenant.id, name="Visita", field_schema={})
    db.add(doc_type)
    await db.commit()
    await _spent(db, tenant, 5.0)

    response = await client.post(
        f"/document-types/{doc_type.id}/template-assistant",
        files={"file": ("x.docx", b"not read", "application/octet-stream")},
        headers=await _admin(db, tenant),
    )

    assert response.status_code == 402
    assert response.json()["detail"] == t("es", "spend_capped")


async def _super_admin(db: AsyncSession) -> dict[str, str]:
    user = TenantUser(
        tenant_id=None,
        email=f"root-{uuid.uuid4().hex[:6]}@reportai.test",
        hashed_password=hash_password("x"),
        full_name="Root",
        role="super_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": None, "ver": 0})
    return {"Authorization": f"Bearer {token}"}


async def test_the_super_admin_moves_a_company_between_plans(client: AsyncClient, db: AsyncSession) -> None:
    tenant, _ = await _company(db, plan="unlimited")
    headers = await _super_admin(db)

    moved = await client.patch(f"/admin/tenants/{tenant.id}", json={"plan": "pro"}, headers=headers)
    assert moved.status_code == 200
    assert (moved.json()["plan"], moved.json()["plan_status"]) == ("pro", "active")
    period_end = moved.json()["plan_period_end"]

    past_due = await client.patch(f"/admin/tenants/{tenant.id}", json={"plan_status": "past_due"}, headers=headers)
    assert past_due.json()["plan_status"] == "past_due"
    assert past_due.json()["plan_period_end"] == period_end  # a status change keeps the period

    unknown = await client.patch(f"/admin/tenants/{tenant.id}", json={"plan": "platinum"}, headers=headers)
    assert unknown.status_code == 422
