"""OPS-3: a deploy or crash kills in-flight pipelines (they run inside the API process) and
leaves their reports 'pending' forever, with the sender never told."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.channel_connection import ChannelConnection
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent import sweeper


@pytest.fixture
def _own_sessions(monkeypatch: pytest.MonkeyPatch, _test_engine) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        sweeper, "AsyncSessionLocal", async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    )


async def _setup(db: AsyncSession) -> tuple[Tenant, ChannelConnection]:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "t"},
        allowed_senders=["1"],
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    return tenant, connection


async def _report(db: AsyncSession, tenant: Tenant, *, status: str, idle_minutes: int) -> Report:
    report = Report(
        tenant_id=tenant.id, status=status, requester_channel="telegram", requester_identifier="1"
    )
    db.add(report)
    await db.commit()
    # An explicit updated_at in the UPDATE suppresses the column's onupdate.
    await db.execute(
        update(Report)
        .where(Report.id == report.id)
        .values(updated_at=text(f"now() - interval '{idle_minutes} minutes'"))
    )
    await db.commit()
    await db.refresh(report)
    return report


async def test_only_pending_reports_without_recent_progress_are_failed_and_their_sender_told(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _own_sessions: None
) -> None:
    tenant, _ = await _setup(db)
    dead = await _report(db, tenant, status="pending", idle_minutes=30)
    slow_but_alive = await _report(db, tenant, status="pending", idle_minutes=30)
    db.add(ExecutionLog(tenant_id=tenant.id, report_id=slow_but_alive.id, step="extract", status="success"))
    fresh = await _report(db, tenant, status="pending", idle_minutes=1)
    waiting_for_a_human = await _report(db, tenant, status="awaiting_approval", idle_minutes=600)
    await db.commit()

    adapter = AsyncMock()
    monkeypatch.setattr(sweeper, "get_channel_adapter", lambda _connection: adapter)

    swept = await sweeper.fail_stuck_reports(older_than=timedelta(minutes=15))

    assert swept == 1
    for report in (dead, slow_but_alive, fresh, waiting_for_a_human):
        await db.refresh(report)
    assert dead.status == "failed"
    assert "no progress" in (dead.error_detail or "")
    assert dead.completed_at is not None
    assert [slow_but_alive.status, fresh.status, waiting_for_a_human.status] == [
        "pending",
        "pending",
        "awaiting_approval",
    ]
    adapter.send_message.assert_awaited_once()
    assert adapter.send_message.await_args.args[0].recipient_id == "1"


async def test_a_second_sweep_does_not_repeat_the_work(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _own_sessions: None
) -> None:
    tenant, _ = await _setup(db)
    await _report(db, tenant, status="pending", idle_minutes=30)
    adapter = AsyncMock()
    monkeypatch.setattr(sweeper, "get_channel_adapter", lambda _connection: adapter)

    assert await sweeper.fail_stuck_reports(older_than=timedelta(minutes=15)) == 1
    assert await sweeper.fail_stuck_reports(older_than=timedelta(minutes=15)) == 0
    adapter.send_message.assert_awaited_once()


async def test_a_reply_to_an_old_paused_report_is_not_swept_right_after_the_claim(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _own_sessions: None
) -> None:
    """The claim flips the status back to 'pending'; without a fresh updated_at the sweep
    would kill a run that resumed seconds ago."""
    from app.repositories.report_repository import ReportRepository

    tenant, _ = await _setup(db)
    paused = await _report(db, tenant, status="awaiting_approval", idle_minutes=600)
    monkeypatch.setattr(sweeper, "get_channel_adapter", lambda _connection: AsyncMock())

    assert await ReportRepository(db).claim_for_resume(paused.id) is True

    assert await sweeper.fail_stuck_reports(older_than=timedelta(minutes=15)) == 0
    await db.refresh(paused)
    assert paused.status == "pending"
