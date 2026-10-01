"""Saving a Telegram bot in the panel registers its webhook with Telegram — previously a
separate manual script, so a freshly connected bot silently received nothing."""

from typing import Any, ClassVar, Self

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.channels import telegram_webhook


class _FakeTelegram:
    """Stands in for httpx.AsyncClient inside the registration service."""

    calls: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    status_code = 200
    body: ClassVar[dict[str, Any]] = {"ok": True, "result": True}
    connect_error = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
        if type(self).connect_error:
            raise httpx.ConnectError(f"boom while calling {url}")  # httpx embeds the URL (and token)
        type(self).calls.append((url, json))
        return httpx.Response(type(self).status_code, json=type(self).body)


@pytest.fixture(autouse=True)
def _telegram(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTelegram]:
    _FakeTelegram.calls = []
    _FakeTelegram.status_code = 200
    _FakeTelegram.body = {"ok": True, "result": True}
    _FakeTelegram.connect_error = False
    monkeypatch.setattr(telegram_webhook.httpx, "AsyncClient", _FakeTelegram)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://app.example.com")
    monkeypatch.setattr(settings, "API_ROOT_PATH", "/api")
    return _FakeTelegram


async def _admin_headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(
        TenantUser(
            tenant_id=tenant.id,
            email="admin@acme.test",
            hashed_password=hash_password("correct-password"),
            full_name="Admin",
            role="tenant_admin",
            is_active=True,
        )
    )
    await db.commit()
    login = await client.post("/auth/login", json={"email": "admin@acme.test", "password": "correct-password"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_payload(bot_token: str = "111:AAA") -> dict[str, Any]:
    return {"channel_type": "telegram", "display_name": "Bot", "credentials": {"bot_token": bot_token}}


async def test_creating_a_bot_registers_its_webhook(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)

    response = await client.post("/channels", json=_create_payload(), headers=headers)

    assert response.status_code == 201
    connection = (await db.execute(select(ChannelConnection))).scalar_one()
    [(url, body)] = _telegram.calls
    assert url == "https://api.telegram.org/bot111:AAA/setWebhook"
    assert body["url"] == f"https://app.example.com/api/webhooks/telegram/{connection.id}"
    assert body["secret_token"] == connection.credentials["secret_token"]
    assert body["allowed_updates"] == ["message", "callback_query"]


async def test_a_token_telegram_refuses_is_reported_and_nothing_is_saved(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)
    _telegram.status_code = 401
    _telegram.body = {"ok": False, "error_code": 401, "description": "Unauthorized"}

    response = await client.post("/channels", json=_create_payload("999:SECRET"), headers=headers)

    assert response.status_code == 400
    assert "Unauthorized" in response.json()["detail"]
    assert "999:SECRET" not in response.text
    assert (await db.execute(select(ChannelConnection))).scalars().all() == []


async def test_telegram_being_unreachable_never_leaks_the_token(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)
    _telegram.connect_error = True

    response = await client.post("/channels", json=_create_payload("999:SECRET"), headers=headers)

    assert response.status_code == 400
    assert "999:SECRET" not in response.text
    assert (await db.execute(select(ChannelConnection))).scalars().all() == []


async def test_without_a_public_url_the_connection_is_saved_without_calling_telegram(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")

    response = await client.post("/channels", json=_create_payload(), headers=headers)

    assert response.status_code == 201
    assert _telegram.calls == []


async def test_other_channels_never_touch_telegram(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)

    response = await client.post(
        "/channels",
        json={"channel_type": "email", "display_name": "Inbox", "credentials": {"inbound_slug": "acme"}},
        headers=headers,
    )

    assert response.status_code == 201
    assert _telegram.calls == []


async def test_updating_registers_again_only_when_telegram_has_something_new_to_learn(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)
    connection_id = (await client.post("/channels", json=_create_payload(), headers=headers)).json()["id"]
    _telegram.calls.clear()
    edit = {"display_name": "Bot", "allowed_senders": ["42"], "is_active": True}

    await client.patch(f"/channels/{connection_id}", json=edit, headers=headers)
    assert _telegram.calls == []  # allowed senders don't depend on Telegram being reachable

    await client.patch(f"/channels/{connection_id}", json={**edit, "credentials": {"bot_token": "222:BBB"}}, headers=headers)
    assert [url for url, _ in _telegram.calls] == ["https://api.telegram.org/bot222:BBB/setWebhook"]

    _telegram.calls.clear()
    await client.patch(f"/channels/{connection_id}", json={**edit, "is_active": False}, headers=headers)
    await client.patch(f"/channels/{connection_id}", json=edit, headers=headers)  # switched back on
    assert len(_telegram.calls) == 1


async def test_an_older_connection_without_a_secret_gets_one_when_its_token_changes(
    client: AsyncClient, db: AsyncSession, _telegram: type[_FakeTelegram]
) -> None:
    headers = await _admin_headers(client, db)
    tenant_id = (await db.execute(select(Tenant.id))).scalar_one()
    old = ChannelConnection(
        tenant_id=tenant_id,
        channel_type="telegram",
        display_name="Old bot",
        credentials={"bot_token": "111:AAA"},
        allowed_senders=[],
        is_active=True,
    )
    db.add(old)
    await db.commit()

    response = await client.patch(
        f"/channels/{old.id}",
        json={"display_name": "Old bot", "credentials": {"bot_token": "333:CCC"}, "allowed_senders": [], "is_active": True},
        headers=headers,
    )

    assert response.status_code == 200
    await db.refresh(old)
    assert old.credentials["secret_token"]
    assert _telegram.calls[0][1]["secret_token"] == old.credentials["secret_token"]
