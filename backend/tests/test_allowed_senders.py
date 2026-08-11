from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent.invoke import start_or_resume_pipeline
from app.services.channels.base import IncomingMessage


async def _create_connection(db: AsyncSession, *, allowed_senders: list[str]) -> ChannelConnection:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "test-token"},
        allowed_senders=allowed_senders,
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection


def _incoming(connection: ChannelConnection, sender_id: str) -> IncomingMessage:
    return IncomingMessage(
        channel_type="telegram",
        channel_connection_id=connection.id,
        sender_id=sender_id,
        text="hello",
        media_reference=None,
        raw_payload={},
    )


async def test_unlisted_sender_rejected_no_report_created(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = await _create_connection(db, allowed_senders=["12345"])
    mock_adapter = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent.invoke.get_channel_adapter", lambda _connection: mock_adapter
    )

    result = await start_or_resume_pipeline(
        db=db,
        connection=connection,
        incoming=_incoming(connection, "99999"),
        background_tasks=BackgroundTasks(),
    )

    assert result is None
    mock_adapter.send_message.assert_awaited_once()
    reports = (await db.execute(select(Report).where(Report.tenant_id == connection.tenant_id))).scalars().all()
    assert len(reports) == 0


async def test_empty_allow_list_allows_any_sender(db: AsyncSession) -> None:
    connection = await _create_connection(db, allowed_senders=[])

    result = await start_or_resume_pipeline(
        db=db,
        connection=connection,
        incoming=_incoming(connection, "anyone"),
        background_tasks=BackgroundTasks(),
    )

    assert result is not None


async def test_allowed_sender_passes_through(db: AsyncSession) -> None:
    connection = await _create_connection(db, allowed_senders=["12345"])

    result = await start_or_resume_pipeline(
        db=db,
        connection=connection,
        incoming=_incoming(connection, "12345"),
        background_tasks=BackgroundTasks(),
    )

    assert result is not None


async def test_resume_branch_also_enforces_allow_list(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = await _create_connection(db, allowed_senders=["12345"])
    pending_report = Report(
        tenant_id=connection.tenant_id,
        status="awaiting_approval",
        requester_channel="telegram",
        requester_identifier="99999",
    )
    db.add(pending_report)
    await db.commit()

    mock_adapter = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent.invoke.get_channel_adapter", lambda _connection: mock_adapter
    )

    result = await start_or_resume_pipeline(
        db=db,
        connection=connection,
        incoming=_incoming(connection, "99999"),
        background_tasks=BackgroundTasks(),
    )

    assert result is None
    mock_adapter.send_message.assert_awaited_once()
