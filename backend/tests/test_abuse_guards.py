"""Cost/abuse guards for the public demo: per-sender rate limit, global daily
spend cap (both at the pipeline's single entry point) and the audio size cap."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent import invoke
from app.services.agent.nodes import media
from app.services.agent.state import AgentState
from app.services.observability import execution_log


async def _create_connection(db: AsyncSession) -> ChannelConnection:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "test-token"},
        allowed_senders=[],
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection


def _incoming(connection: ChannelConnection, sender_id: str = "12345") -> Any:
    from app.services.channels.base import IncomingMessage

    return IncomingMessage(
        channel_type="telegram",
        channel_connection_id=connection.id,
        sender_id=sender_id,
        text="hello",
        media_reference=None,
        raw_payload={},
    )


def _report(connection: ChannelConnection, *, status: str = "delivered") -> Report:
    return Report(
        tenant_id=connection.tenant_id,
        status=status,
        requester_channel="telegram",
        requester_identifier="12345",
    )


@pytest.fixture
def _adapter_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(invoke, "get_channel_adapter", lambda _connection: mock)
    return mock


async def test_rate_limited_sender_gets_no_new_report(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _adapter_mock: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "SENDER_RATE_LIMIT_PER_HOUR", 2)
    connection = await _create_connection(db)
    db.add_all([_report(connection), _report(connection)])
    await db.commit()

    result = await invoke.start_or_resume_pipeline(
        db=db, connection=connection, incoming=_incoming(connection), background_tasks=BackgroundTasks()
    )

    assert result is None
    _adapter_mock.send_message.assert_awaited_once()
    count = len((await db.execute(select(Report))).scalars().all())
    assert count == 2  # nothing new created


async def test_reply_to_paused_report_is_never_rate_limited(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SENDER_RATE_LIMIT_PER_HOUR", 1)
    connection = await _create_connection(db)
    paused = _report(connection, status="awaiting_approval")
    db.add_all([paused, _report(connection), _report(connection)])
    await db.commit()
    await db.refresh(paused)

    result = await invoke.start_or_resume_pipeline(
        db=db, connection=connection, incoming=_incoming(connection), background_tasks=BackgroundTasks()
    )

    assert result == paused.id


async def test_daily_spend_cap_blocks_everything(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _adapter_mock: AsyncMock
) -> None:
    monkeypatch.setattr(settings, "DAILY_SPEND_CAP_USD", 0.5)
    connection = await _create_connection(db)
    db.add(
        ExecutionLog(
            tenant_id=connection.tenant_id,
            report_id=None,
            step="extract",
            status="success",
            cost_usd=0.6,
        )
    )
    await db.commit()

    result = await invoke.start_or_resume_pipeline(
        db=db, connection=connection, incoming=_incoming(connection), background_tasks=BackgroundTasks()
    )

    assert result is None
    _adapter_mock.send_message.assert_awaited_once()


async def test_oversized_audio_is_rejected(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _test_engine: Any
) -> None:
    monkeypatch.setattr(
        execution_log,
        "AsyncSessionLocal",
        async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False),
    )
    monkeypatch.setattr(settings, "MAX_AUDIO_BYTES", 10)
    connection = await _create_connection(db)
    report = _report(connection, status="pending")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    monkeypatch.setattr(media, "_load_connection", AsyncMock(return_value=connection))
    adapter = AsyncMock()
    adapter.download_media = AsyncMock(return_value=b"x" * 100)
    monkeypatch.setattr(media, "get_channel_adapter", lambda _connection: adapter)

    state = AgentState(
        thread_id=str(report.id),
        tenant_id=connection.tenant_id,
        channel_connection_id=connection.id,
        channel_type="telegram",
        sender_id="12345",
        report_id=report.id,
        raw_payload={},
        media_reference="file-id",
    )

    with pytest.raises(ValueError, match="Audio too large"):
        await media.download_media_node(state)
