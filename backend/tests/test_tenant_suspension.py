"""A deactivated company is locked out everywhere at once: sessions it already holds, new
sign-ins, refreshes, reset emails and its channels. Other companies notice nothing."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.agent import ingestion
from app.services.agent.ingestion import ingest_message
from app.services.channels.base import IncomingMessage
from app.services.i18n import t

PASSWORD = "correct-password"


async def _company(db: AsyncSession, name: str) -> tuple[Tenant, TenantUser]:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True, language="es")
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"admin@{name.lower()}.test",
        hashed_password=hash_password(PASSWORD),
        full_name="Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return tenant, user


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return dict(response.json())


async def _suspend(db: AsyncSession, tenant: Tenant) -> None:
    tenant.is_active = False
    await db.commit()


async def test_suspension_ends_the_sessions_a_company_already_holds(client: AsyncClient, db: AsyncSession) -> None:
    acme, acme_admin = await _company(db, "Acme")
    _, other_admin = await _company(db, "Other")
    acme_tokens = await _login(client, acme_admin.email)
    other_tokens = await _login(client, other_admin.email)

    await _suspend(db, acme)

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {acme_tokens['access_token']}"})
    refreshed = await client.post("/auth/refresh", json={"refresh_token": acme_tokens["refresh_token"]})
    assert me.status_code == 401
    assert refreshed.status_code == 401

    other_me = await client.get("/auth/me", headers={"Authorization": f"Bearer {other_tokens['access_token']}"})
    assert other_me.status_code == 200


async def test_a_suspended_company_cannot_sign_in_or_get_a_reset_email(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, acme_admin = await _company(db, "Acme")
    await _suspend(db, acme)
    send = AsyncMock()
    monkeypatch.setattr("app.api.auth.send_plain_email", send)

    login = await client.post("/auth/login", json={"email": acme_admin.email, "password": PASSWORD})
    forgot = await client.post("/auth/forgot-password", json={"email": acme_admin.email})

    assert login.status_code == 401
    assert login.json() == (await client.post("/auth/login", json={"email": "nobody@x.test", "password": "x"})).json()
    assert forgot.status_code == 200  # same answer as for an unknown address
    send.assert_not_awaited()


async def test_the_super_admin_has_no_company_to_be_suspended(client: AsyncClient, db: AsyncSession) -> None:
    db.add(
        TenantUser(
            tenant_id=None,
            email="root@reportai.test",
            hashed_password=hash_password(PASSWORD),
            full_name="Root",
            role="super_admin",
            is_active=True,
        )
    )
    await db.commit()

    tokens = await _login(client, "root@reportai.test")

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200


async def test_a_suspended_company_s_channel_answers_but_starts_nothing(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    acme, _ = await _company(db, "Acme")
    connection = ChannelConnection(
        tenant_id=acme.id,
        channel_type="telegram",
        display_name="Bot",
        credentials={"bot_token": "t"},
        allowed_senders=[],
        is_active=True,
    )
    db.add(connection)
    await db.commit()
    adapter = AsyncMock()
    monkeypatch.setattr(ingestion, "get_channel_adapter", lambda _connection: adapter)
    await _suspend(db, acme)

    result = await ingest_message(
        db=db,
        connection=connection,
        incoming=IncomingMessage(
            channel_type="telegram",
            channel_connection_id=connection.id,
            sender_id="42",
            text="Visité la obra de Alicante",
            raw_payload={},
        ),
    )
    await db.commit()

    assert result.outcome == "rejected"
    assert (await db.execute(select(Report))).scalars().all() == []
    adapter.send_message.assert_awaited_once()
    assert adapter.send_message.await_args.args[0].text == t("es", "tenant_suspended")
