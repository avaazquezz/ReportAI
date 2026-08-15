"""Webhook auth for Telegram — the only channel without an HMAC check until Phase 4.
Telegram echoes the secret registered via setWebhook in the
X-Telegram-Bot-Api-Secret-Token header; the route must verify it when present."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant

_UPDATE: dict[str, Any] = {"message": {"chat": {"id": 123456}, "text": "hello"}}


async def _create_connection(
    db: AsyncSession, *, credentials: dict[str, Any], is_active: bool = True
) -> ChannelConnection:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name="Bot",
        credentials=credentials,
        allowed_senders=[],
        is_active=is_active,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection


@pytest.fixture
def _pipeline_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr("app.api.webhooks.telegram.start_or_resume_pipeline", mock)
    return mock


async def test_valid_secret_accepted(
    client: AsyncClient, db: AsyncSession, _pipeline_mock: AsyncMock
) -> None:
    connection = await _create_connection(
        db, credentials={"bot_token": "t", "secret_token": "s3cret"}
    )

    response = await client.post(
        f"/webhooks/telegram/{connection.id}",
        json=_UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )

    assert response.status_code == 200
    _pipeline_mock.assert_awaited_once()


async def test_wrong_or_missing_secret_rejected(
    client: AsyncClient, db: AsyncSession, _pipeline_mock: AsyncMock
) -> None:
    connection = await _create_connection(
        db, credentials={"bot_token": "t", "secret_token": "s3cret"}
    )

    wrong = await client.post(
        f"/webhooks/telegram/{connection.id}",
        json=_UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
    )
    missing = await client.post(f"/webhooks/telegram/{connection.id}", json=_UPDATE)

    assert wrong.status_code == 401
    assert missing.status_code == 401
    _pipeline_mock.assert_not_awaited()


async def test_connection_without_secret_still_accepted(
    client: AsyncClient, db: AsyncSession, _pipeline_mock: AsyncMock
) -> None:
    # Enforce-if-present: connections created before secrets existed keep working.
    connection = await _create_connection(db, credentials={"bot_token": "t"})

    response = await client.post(f"/webhooks/telegram/{connection.id}", json=_UPDATE)

    assert response.status_code == 200
    _pipeline_mock.assert_awaited_once()


async def test_inactive_connection_is_404(
    client: AsyncClient, db: AsyncSession, _pipeline_mock: AsyncMock
) -> None:
    connection = await _create_connection(db, credentials={"bot_token": "t"}, is_active=False)

    response = await client.post(f"/webhooks/telegram/{connection.id}", json=_UPDATE)

    assert response.status_code == 404
    _pipeline_mock.assert_not_awaited()
