"""Letting a person write to a channel without copying chat ids: an invitation with a one-time
code, opened as a Telegram link or sent as a message."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.models.sender_invite import SenderInvite
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.agent import ingestion
from app.services.agent.ingestion import ingest_message
from app.services.channels.base import IncomingMessage


@pytest.fixture(autouse=True)
def closed_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALLOW_ANY_SENDER", False)


@pytest.fixture
def bot(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    adapter = AsyncMock()
    monkeypatch.setattr(ingestion, "get_channel_adapter", lambda _connection: adapter)
    return adapter


async def _admin(db: AsyncSession, role: str = "tenant_admin") -> TenantUser:
    tenant = Tenant(name="Reformas García", slug=f"garcia-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id, email=f"{uuid.uuid4().hex[:6]}@garcia.test", hashed_password=hash_password("pw-12345678"),
        full_name="Lucía", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": "pw-12345678"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _bot_and_admin(client: AsyncClient, db: AsyncSession) -> tuple[dict[str, Any], dict[str, str]]:
    headers = await _headers(client, await _admin(db))
    created = await client.post(
        "/channels", json={"channel_type": "telegram", "display_name": "Bot", "credentials": {"bot_token": "1:A"}}, headers=headers
    )
    return created.json(), headers


def _message(connection_id: str, text: str, sender: str = "777", **extra: Any) -> IncomingMessage:
    return IncomingMessage(
        channel_type="telegram", channel_connection_id=uuid.UUID(connection_id), sender_id=sender, text=text,
        raw_payload={}, **extra,
    )


async def _ingest(db: AsyncSession, connection_id: str, text: str, sender: str = "777") -> str:
    connection = await db.get(ChannelConnection, uuid.UUID(connection_id))
    assert connection is not None
    result = await ingest_message(db=db, connection=connection, incoming=_message(connection_id, text, sender))
    await db.commit()
    return result.outcome


async def test_opening_the_telegram_link_lets_the_person_in(client: AsyncClient, db: AsyncSession, bot: AsyncMock) -> None:
    channel, headers = await _bot_and_admin(client, db)

    invite = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "Ana Ruiz"}, headers=headers)).json()

    code = invite["code"]
    assert len(code) == 9 and code[4] == "-"
    assert invite["link"] == f"https://t.me/acme_bot?start={code.replace('-', '')}"
    assert await _ingest(db, channel["id"], f"/start {code.replace('-', '')}") == "replied"
    assert "Ana Ruiz" in bot.send_message.await_args.args[0].text
    refreshed = (await client.get(f"/channels/{channel['id']}", headers=headers)).json()
    assert refreshed["allowed_senders"] == ["777"] and refreshed["sender_labels"] == {"777": "Ana Ruiz"}

    assert await _ingest(db, channel["id"], "Visité la obra de Alicante") == "created"


async def test_a_code_works_once_and_only_on_its_own_channel(client: AsyncClient, db: AsyncSession, bot: AsyncMock) -> None:
    channel, headers = await _bot_and_admin(client, db)
    other = await client.post(
        "/channels", json={"channel_type": "telegram", "display_name": "Otro", "credentials": {"bot_token": "2:B"}}, headers=headers
    )
    code = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "Ana"}, headers=headers)).json()["code"]

    assert await _ingest(db, other.json()["id"], code, sender="555") == "rejected"
    assert await _ingest(db, channel["id"], code.lower(), sender="777") == "replied"  # typed any old way
    assert await _ingest(db, channel["id"], code, sender="888") == "rejected"  # already used


async def test_an_expired_or_revoked_code_does_nothing(client: AsyncClient, db: AsyncSession, bot: AsyncMock) -> None:
    channel, headers = await _bot_and_admin(client, db)
    expired = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "A"}, headers=headers)).json()
    revoked = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "B"}, headers=headers)).json()
    row = await db.get(SenderInvite, uuid.UUID(expired["id"]))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()

    assert (await client.delete(f"/channels/{channel['id']}/invites/{revoked['id']}", headers=headers)).status_code == 204

    assert await _ingest(db, channel["id"], expired["code"]) == "rejected"
    assert await _ingest(db, channel["id"], revoked["code"]) == "rejected"
    listed = (await client.get(f"/channels/{channel['id']}/invites", headers=headers)).json()
    assert [i["label"] for i in listed] == ["A"]


async def test_a_used_invitation_cannot_be_revoked(client: AsyncClient, db: AsyncSession, bot: AsyncMock) -> None:
    channel, headers = await _bot_and_admin(client, db)
    invite = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "A"}, headers=headers)).json()
    await _ingest(db, channel["id"], invite["code"])

    assert (await client.delete(f"/channels/{channel['id']}/invites/{invite['id']}", headers=headers)).status_code == 409


async def test_the_start_button_is_answered_not_turned_into_a_report(
    client: AsyncClient, db: AsyncSession, bot: AsyncMock
) -> None:
    channel, headers = await _bot_and_admin(client, db)
    code = (await client.post(f"/channels/{channel['id']}/invites", json={"label": "Ana"}, headers=headers)).json()["code"]
    await _ingest(db, channel["id"], code)

    assert await _ingest(db, channel["id"], "/start") == "replied"

    assert "nota de voz" in bot.send_message.await_args.args[0].text
    assert (await db.scalars(select(Report))).all() == []


async def test_only_admins_invite(client: AsyncClient, db: AsyncSession) -> None:
    channel, _ = await _bot_and_admin(client, db)
    approver = await _admin(db, "approver")

    response = await client.post(f"/channels/{channel['id']}/invites", json={"label": "A"}, headers=await _headers(client, approver))

    assert response.status_code == 403
