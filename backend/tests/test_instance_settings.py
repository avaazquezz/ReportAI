"""The AI provider, transcription and mail server are entered in the panel: stored encrypted,
never sent back, winning over the environment, and tried before they are saved."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import instance_settings, llm
from app.services.delivery import email as smtp_delivery

AI = {
    "extraction": {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-ant-api03-secret-1234"},
    "transcription": {"base_url": "https://api.groq.com/openai/v1", "model": "whisper-large-v3-turbo", "api_key": "gsk_secret_5678"},
}
EMAIL = {"host": "smtp.acme.test", "port": 587, "security": "starttls", "user": "bot", "password": "mail-pass-9999", "from_address": "informes@acme.test"}


async def _user(db: AsyncSession, role: str = "tenant_admin") -> TenantUser:
    tenant = None
    if role != "super_admin":
        tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
        db.add(tenant)
        await db.flush()
    user = TenantUser(
        tenant_id=tenant.id if tenant else None, email=f"{uuid.uuid4().hex[:8]}@acme.test",
        hashed_password=hash_password("correct-password"), full_name="Admin", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": "correct-password"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def single_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)


async def test_keys_are_stored_encrypted_and_never_sent_back(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None
) -> None:
    headers = await _headers(client, await _user(db))

    saved = await client.put("/instance/ai", json=AI, headers=headers)

    assert saved.status_code == 200
    body = saved.json()
    assert "sk-ant-api03-secret-1234" not in saved.text and "gsk_secret_5678" not in saved.text
    assert body["extraction"]["api_key"] == {"is_set": True, "hint": "…1234"}
    assert body["extraction"]["configured"] is True and body["transcription"]["configured"] is True
    raw = (await db.execute(text("SELECT value FROM instance_settings WHERE key = 'extraction_api_key'"))).scalar_one()
    assert "secret" not in raw


async def test_a_key_saved_in_the_panel_wins_over_the_environment(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-from-env")
    headers = await _headers(client, await _user(db))
    await client.put("/instance/ai", json=AI, headers=headers)
    await db.commit()
    used_keys: list[str] = []

    def client_for(api_key: str) -> SimpleNamespace:
        used_keys.append(api_key)
        create = AsyncMock(return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')], stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        ))
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    monkeypatch.setattr(llm, "_anthropic_client", client_for)

    class Ping(BaseModel):
        ok: bool

    result = await llm.structured_completion(system="s", user="u", model_cls=Ping, tool_name="t")

    assert used_keys == ["sk-ant-api03-secret-1234"] and result.model == "claude-sonnet-5"


async def test_changing_provider_needs_the_new_providers_key(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None
) -> None:
    headers = await _headers(client, await _user(db))
    await client.put("/instance/ai", json=AI, headers=headers)

    switched = {**AI, "extraction": {"provider": "openai_compatible", "model": "deepseek-chat", "base_url": "https://api.deepseek.com"}}
    refused = await client.put("/instance/ai", json=switched, headers=headers)
    assert refused.status_code == 400 and "new provider" in refused.json()["detail"]

    accepted = await client.put(
        "/instance/ai", json={**switched, "extraction": {**switched["extraction"], "api_key": "sk-deepseek-0000"}}, headers=headers
    )
    assert accepted.status_code == 200 and accepted.json()["extraction"]["api_key"]["hint"] == "…0000"

    kept = await client.put(  # the same provider again: the saved key stays
        "/instance/ai", json={**switched, "extraction": {**switched["extraction"], "model": "deepseek-reasoner"}}, headers=headers
    )
    assert kept.status_code == 200 and kept.json()["extraction"]["api_key"]["hint"] == "…0000"


async def test_an_empty_secret_falls_back_to_the_environment(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "env-password")
    headers = await _headers(client, await _user(db))
    await client.put("/instance/email", json=EMAIL, headers=headers)
    assert (await instance_settings.smtp_config(db)).password == "mail-pass-9999"

    await client.put("/instance/email", json={**EMAIL, "password": ""}, headers=headers)

    assert (await instance_settings.smtp_config(db)).password == "env-password"


async def test_only_the_installations_admin_reaches_its_settings(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, stored_instance_settings: None
) -> None:
    company_admin = await _headers(client, await _user(db))
    super_admin = await _headers(client, await _user(db, "super_admin"))

    monkeypatch.setattr(settings, "SINGLE_TENANT", False)  # a server hosting several companies
    assert (await client.get("/instance/ai", headers=company_admin)).status_code == 403
    assert (await client.get("/instance/ai", headers=super_admin)).status_code == 200

    monkeypatch.setattr(settings, "SINGLE_TENANT", True)  # one company: its admin runs it
    assert (await client.get("/instance/email", headers=company_admin)).status_code == 200
    assert (await client.get("/instance/email", headers=super_admin)).status_code == 403


async def test_a_test_email_tries_the_settings_as_typed_and_reports_the_failure(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send = AsyncMock()
    monkeypatch.setattr(smtp_delivery.aiosmtplib, "send", send)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    headers = await _headers(client, await _user(db))

    ok = await client.post("/instance/email/check", json={"to": "ana@acme.test", "settings": EMAIL}, headers=headers)

    assert ok.json() == {"ok": True, "detail": None}
    assert send.await_args.kwargs["hostname"] == "smtp.acme.test" and send.await_args.kwargs["password"] == "mail-pass-9999"
    assert (await client.get("/instance/email", headers=headers)).json()["configured"] is False  # nothing saved

    send.side_effect = ConnectionRefusedError("connection refused")
    failed = await client.post("/instance/email/check", json={"to": "ana@acme.test", "settings": EMAIL}, headers=headers)
    assert failed.json()["ok"] is False and "connection refused" in failed.json()["detail"]


async def test_the_ai_check_calls_the_model_as_typed_without_saving(
    client: AsyncClient, db: AsyncSession, single_tenant: None, stored_instance_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def client_for(api_key: str, base_url: str) -> SimpleNamespace:
        calls.append((api_key, base_url))
        create = AsyncMock(side_effect=RuntimeError("Error code: 401 - invalid api key"))
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(llm, "_openai_client", client_for)
    headers = await _headers(client, await _user(db))
    typed = {"provider": "openai_compatible", "model": "deepseek-chat", "base_url": "https://api.deepseek.com", "api_key": "sk-typo"}

    result = await client.post("/instance/ai/check", json={"extraction": typed}, headers=headers)

    assert result.json() == {"ok": False, "detail": "RuntimeError: Error code: 401 - invalid api key"}
    assert calls == [("sk-typo", "https://api.deepseek.com")]
    assert (await instance_settings.load(db)) == {}
