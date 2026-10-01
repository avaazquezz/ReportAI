"""Telegram without a public address: the worker asks Telegram for updates (getUpdates), each one
is ingested before it is acknowledged, and only one worker polls at a time."""

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant
from app.services.channels import telegram_updates, telegram_webhook
from app.services.channels.telegram_updates import poll_once


def _update(update_id: int, text_: str) -> dict[str, Any]:
    return {"update_id": update_id, "message": {"chat": {"id": 42}, "date": 1786000000, "text": text_}}


async def _connection(db: AsyncSession) -> ChannelConnection:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id, channel_type="telegram", display_name="Bot",
        credentials={"bot_token": "123:ABC"}, allowed_senders=[], is_active=True,
    )
    db.add(connection)
    await db.commit()
    return connection


def _telegram(updates: list[dict[str, Any]], seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": updates})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_each_update_is_ingested_then_acknowledged_by_the_next_offset(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = await _connection(db)
    ingest = AsyncMock()
    monkeypatch.setattr(telegram_updates, "ingest_message", ingest)
    seen: list[httpx.Request] = []

    async with _telegram([_update(901, "Visité la obra"), _update(902, "Y el almacén")], seen) as client:
        offset = await poll_once(client, "123:ABC", connection.id, 900)

    assert offset == 903
    assert [call.kwargs["incoming"].text for call in ingest.await_args_list] == ["Visité la obra", "Y el almacén"]
    assert ingest.await_args_list[0].kwargs["incoming"].external_id == "901"  # redeliveries are recognised
    body = json.loads(seen[0].content)
    assert (body["offset"], body["allowed_updates"]) == (900, ["message", "callback_query"])
    assert body["timeout"] == telegram_updates.POLL_TIMEOUT_SECONDS


async def test_an_update_that_keeps_failing_is_skipped_not_retried_forever(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = await _connection(db)
    ingest = AsyncMock(side_effect=[RuntimeError("db down")] * 3 + [None])
    monkeypatch.setattr(telegram_updates, "ingest_message", ingest)
    monkeypatch.setattr(telegram_updates.asyncio, "sleep", AsyncMock())

    async with _telegram([_update(5, "uno"), _update(6, "dos")], []) as client:
        offset = await poll_once(client, "123:ABC", connection.id, None)

    assert offset == 7 and ingest.await_count == 4  # three tries for the first, one for the second


async def test_a_switched_off_connection_ingests_nothing(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = await _connection(db)
    connection.is_active = False
    await db.commit()
    ingest = AsyncMock()
    monkeypatch.setattr(telegram_updates, "ingest_message", ingest)

    async with _telegram([_update(1, "hola")], []) as client:
        assert await poll_once(client, "123:ABC", connection.id, None) == 2

    ingest.assert_not_awaited()


async def test_a_wrong_token_is_refused_without_repeating_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    real = httpx.AsyncClient
    monkeypatch.setattr(telegram_webhook.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))

    with pytest.raises(ValidationException) as refused:
        await telegram_webhook.verify_telegram_bot("999:SECRET")

    assert "Unauthorized" in str(refused.value.detail) and "999:SECRET" not in str(refused.value.detail)


async def test_only_one_worker_polls(_test_engine: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram_updates, "engine", _test_engine)
    monkeypatch.setattr(telegram_updates, "REFRESH_SECONDS", 0.05)
    leading = asyncio.Event()

    async def lead(stopping: asyncio.Event, still_leading: Any) -> None:
        leading.set()
        await stopping.wait()

    monkeypatch.setattr(telegram_updates, "_poll_while_leading", lead)
    stopping = asyncio.Event()

    async with _test_engine.connect() as other_worker:
        await other_worker.execute(text("SELECT pg_advisory_lock(:k)"), {"k": telegram_updates._LOCK_KEY})
        poller = asyncio.create_task(telegram_updates.run_pollers(stopping))
        await asyncio.sleep(0.3)
        assert not leading.is_set()  # someone else polls: this worker stands by

        await other_worker.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": telegram_updates._LOCK_KEY})
        await asyncio.wait_for(leading.wait(), timeout=2)  # and takes over when they stop

    stopping.set()
    await asyncio.wait_for(poller, timeout=2)
