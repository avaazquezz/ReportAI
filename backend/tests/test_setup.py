"""A fresh one-company installation is set up from the panel, but only by whoever holds the
one-time code printed on the server: never by the first stranger to find its address."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.api import setup as setup_api
from app.core.config import settings
from app.models.channel_connection import ChannelConnection
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import instance_settings
from app.services.setup import issue_setup_code

WIZARD = {
    "company": {"name": "Reformas García & Hijos", "language": "es", "timezone": "Europe/Madrid"},
    "admin": {"full_name": "Lucía García", "email": "lucia@garcia.test", "password": "a-long-password"},
    "extraction": {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-ant-api03-wizard-1234"},
    "transcription": {"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3-turbo", "api_key": "gsk_wizard"},
    "telegram_bot_token": "123:ABC",
}


@pytest.fixture(autouse=True)
def single_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)


@pytest.fixture
def telegram(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(setup_api, "verify_telegram_bot", AsyncMock(return_value="garcia_bot"))
    register = AsyncMock(return_value=False)
    monkeypatch.setattr(setup_api, "register_telegram_webhook", register)
    return register


async def _code(db: AsyncSession) -> str:
    code = await issue_setup_code(db)
    await db.commit()
    return code


async def test_a_fresh_installation_asks_to_be_set_up(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await client.get("/setup/status")).json() == {"single_tenant": True, "needs_setup": True}

    monkeypatch.setattr(settings, "SINGLE_TENANT", False)  # a server hosting several companies
    assert (await client.get("/setup/status")).json() == {"single_tenant": False, "needs_setup": False}


async def test_the_wizard_creates_the_company_its_admin_and_its_settings_in_one_go(
    client: AsyncClient, db: AsyncSession, telegram: AsyncMock, stored_instance_settings: None
) -> None:
    code = await _code(db)

    done = await client.post("/setup/complete", json={**WIZARD, "code": code.lower()})  # typed any old way

    assert done.status_code == 200
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {done.json()['access_token']}"})
    assert me.json()["email"] == "lucia@garcia.test" and me.json()["role"] == "tenant_admin"
    tenant = (await db.scalars(select(Tenant))).one()
    assert (tenant.name, tenant.slug, tenant.language) == ("Reformas García & Hijos", "reformas-garcia-hijos", "es")
    assert (await instance_settings.ai_config(db)).api_key == "sk-ant-api03-wizard-1234"
    assert (await instance_settings.transcription_config(db)).api_key == "gsk_wizard"
    bot = (await db.scalars(select(ChannelConnection))).one()
    assert bot.credentials["bot_username"] == "garcia_bot" and bot.display_name == "@garcia_bot"

    again = await client.post("/setup/complete", json={**WIZARD, "code": code})
    assert again.status_code == 409  # set up once, for good
    assert (await client.get("/setup/status")).json()["needs_setup"] is False


async def test_without_the_code_nobody_sets_it_up(
    client: AsyncClient, db: AsyncSession, telegram: AsyncMock, stored_instance_settings: None
) -> None:
    await _code(db)

    for path in ("/setup/verify", "/setup/check-ai", "/setup/check-telegram"):
        response = await client.post(path, json={"code": "AAAA-BBBB-CCCC", "bot_token": "x"})
        assert response.status_code == 400, path
    response = await client.post("/setup/complete", json={**WIZARD, "code": "AAAA-BBBB-CCCC"})

    assert response.status_code == 400 and "reportai setup-code" in response.json()["detail"]
    assert (await db.scalars(select(TenantUser))).all() == []


async def test_guessing_codes_is_cut_off(client: AsyncClient, db: AsyncSession, stored_instance_settings: None) -> None:
    await _code(db)
    for _ in range(10):
        await client.post("/setup/verify", json={"code": "WRONG"})

    assert (await client.post("/setup/verify", json={"code": "WRONG"})).status_code == 429


async def test_an_expired_code_no_longer_works(client: AsyncClient, db: AsyncSession, stored_instance_settings: None) -> None:
    code = await _code(db)
    await instance_settings.save(db, {"setup_code_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()})
    await db.commit()

    assert (await client.post("/setup/verify", json={"code": code})).status_code == 400


async def test_a_new_code_replaces_the_old_one(client: AsyncClient, db: AsyncSession, stored_instance_settings: None) -> None:
    old = await _code(db)
    new = await _code(db)

    assert (await client.post("/setup/verify", json={"code": old})).status_code == 400
    assert (await client.post("/setup/verify", json={"code": new})).status_code == 204


async def test_the_cli_prints_a_code_until_the_installation_is_set_up(
    db: AsyncSession, own_sessions: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await cli.setup_code() == 0
    printed = capsys.readouterr().out
    assert "Setup code: " in printed and "/setup" in printed

    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantUser(tenant_id=tenant.id, email="a@acme.test", hashed_password="x", full_name="A", role="tenant_admin"))
    await db.commit()

    assert await cli.setup_code() == 1
    assert "already set up" in capsys.readouterr().err


async def test_the_cli_gives_a_password_link_when_there_is_no_email(
    db: AsyncSession, own_sessions: None, capsys: pytest.CaptureFixture[str]
) -> None:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantUser(tenant_id=tenant.id, email="a@acme.test", hashed_password="x", full_name="A", role="tenant_admin"))
    await db.commit()

    assert await cli.password_link("a@acme.test") == 0
    assert "/reset-password?token=" in capsys.readouterr().out
    assert await cli.password_link("nobody@acme.test") == 1
