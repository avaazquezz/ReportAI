"""Each company's own AI on the hosted service: entered by its admin, stored encrypted, never
sent back, used for its reports only, never replaced by the platform's key, sent only to the
provider addresses ReportAI knows (no URL to type: SSRF), and left out of the platform's spend."""

import contextlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
import pytest
from docx import Document as DocxDocument
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import company_ai as company_ai_api
from app.api.admin import template_assistant as template_assistant_api
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.audit_event import AuditEvent
from app.models.company_setting import CompanySetting
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.execution_log_repository import ExecutionLogRepository
from app.schemas.company_ai import ExtractionProviderId, TranscriptionProviderId
from app.services import (
    company_ai,
    data_lifecycle,
    export,
    instance_settings,
    llm,
    plans,
    transcription,
)
from app.services.agent.nodes import doctype as doctype_node
from app.services.agent.nodes import media as media_node
from app.services.agent.nodes.extract import extract_node
from app.services.agent.state import AgentState, ToolUsage
from app.services.agent.tools import intent as intent_tool
from app.services.agent.tools.pricing import transcription_usage, usage_of
from app.services.ai_providers import EXTRACTION_PROVIDERS, TRANSCRIPTION_PROVIDERS
from app.services.instance_settings import AIConfig, ProviderRejectedKeyError, TranscriptionConfig
from app.services.jobs import runner
from app.services.jobs.errors import PermanentJobError
from app.services.jobs.queue import ClaimedJob, FailOutcome
from app.services.observability.execution_log import write_execution_log
from app.services.settings_checks import CheckFailed, check_ai
from app.services.templates import assistant as template_assistant

PASSWORD = "correct-password"
OWN = {
    "extraction": {"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-ant-company-key-1234"},
    "transcription": {"provider": "groq", "model": "whisper-large-v3-turbo", "api_key": "gsk_company_key_5678"},
}


@pytest.fixture(autouse=True)
def _platform_keys_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # The platform's own keys are there: a company must still never end up using them.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-PLATFORM-key")
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "gsk_PLATFORM_key")
    monkeypatch.setattr(settings, "SINGLE_TENANT", False)


async def _company(db: AsyncSession, *, platform_ai: bool = False, name: str = "Acme") -> Tenant:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True, platform_ai=platform_ai)
    db.add(tenant)
    await db.commit()
    return tenant


async def _member(db: AsyncSession, tenant: Tenant, role: str = "tenant_admin") -> TenantUser:
    user = TenantUser(
        tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:6]}@acme.test",
        hashed_password=hash_password(PASSWORD), full_name=role, role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser) -> dict[str, str]:
    if user.role == "technician":  # they sign in by emailed link, not with a password
        token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": 0})
        return {"Authorization": f"Bearer {token}"}
    response = await client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _admin(client: AsyncClient, db: AsyncSession, **company: bool) -> tuple[Tenant, dict[str, str]]:
    tenant = await _company(db, **company)
    return tenant, await _headers(client, await _member(db, tenant))


# ── Which AI a company uses ──────────────────────────────────────────────────────────────


async def test_the_provider_lists_match_what_the_api_accepts() -> None:
    assert set(get_args(ExtractionProviderId)) == set(EXTRACTION_PROVIDERS)
    assert set(get_args(TranscriptionProviderId)) == set(TRANSCRIPTION_PROVIDERS)


async def test_a_company_without_its_own_key_never_falls_back_to_the_platforms(
    db: AsyncSession, own_ai_keys: None
) -> None:
    tenant = await _company(db)

    extraction = await company_ai.extraction_config(db, tenant)
    transcription = await company_ai.transcription_config(db, tenant)

    assert not extraction.configured and not transcription.configured
    assert "PLATFORM" not in extraction.api_key + transcription.api_key


async def test_a_companys_own_key_is_stored_encrypted_and_paid_by_the_company(
    db: AsyncSession, own_ai_keys: None
) -> None:
    tenant = await _company(db)
    await company_ai.save(db, tenant.id, {"extraction_provider": "openai", "extraction_model": "gpt-6.1-terra",
                                          "extraction_api_key": "sk-proj-company-openai-key"})
    await db.commit()

    config = await company_ai.extraction_config(db, tenant)

    assert config == AIConfig(
        provider="openai_compatible", model="gpt-6.1-terra", api_key="sk-proj-company-openai-key",
        base_url="https://api.openai.com/v1", effort="", platform_paid=False, reasoning_effort="none",
    )
    raw = await db.scalar(text("SELECT value FROM company_settings WHERE key = 'extraction_api_key'"))
    assert raw and "company-openai-key" not in raw


async def test_no_stored_value_can_point_the_worker_at_another_address(db: AsyncSession, own_ai_keys: None) -> None:
    tenant = await _company(db)
    # Whatever reached the table, the address comes from the provider list alone.
    await company_ai.save(db, tenant.id, {
        "extraction_provider": "anthropic", "extraction_api_key": "sk-ant-x" * 3,
        "extraction_base_url": "http://gotenberg:3000", "transcription_provider": "evil",
        "transcription_base_url": "http://postgres:5432", "transcription_api_key": "k" * 12,
    })
    await db.commit()

    extraction = await company_ai.extraction_config(db, tenant)
    transcription = await company_ai.transcription_config(db, tenant)

    assert extraction.base_url == "" and extraction.provider == "anthropic"
    assert not transcription.configured and transcription.base_url == ""


async def test_a_company_on_the_platforms_ai_and_a_one_company_install_use_the_installations(
    db: AsyncSession, own_ai_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = await _company(db, platform_ai=True)
    own = await _company(db, name="Other")
    await company_ai.save(db, own.id, {"extraction_provider": "anthropic", "extraction_api_key": "sk-ant-own-key-0000"})
    await db.commit()

    assert (await company_ai.extraction_config(db, platform)).api_key == "sk-ant-PLATFORM-key"
    assert (await company_ai.extraction_config(db, platform)).platform_paid
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)  # an installation's company: its settings, whatever it stored
    assert (await company_ai.extraction_config(db, own)).api_key == "sk-ant-PLATFORM-key"


# ── The panel: /company/ai ───────────────────────────────────────────────────────────────


async def test_the_admin_sets_its_ai_and_the_key_never_comes_back(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    tenant, headers = await _admin(client, db)

    empty = (await client.get("/company/ai", headers=headers)).json()
    saved = await client.put("/company/ai", json=OWN, headers=headers)

    assert empty["platform_ai"] is False and not empty["extraction"]["configured"]
    assert [p["id"] for p in empty["extraction_providers"]] == list(EXTRACTION_PROVIDERS)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["extraction"] == {"provider": "anthropic", "model": "claude-sonnet-5", "effort": "",
                                  "api_key": {"is_set": True, "hint": "…1234"}, "configured": True}
    assert body["transcription"]["provider"] == "groq" and body["transcription"]["configured"]
    assert "company-key" not in saved.text
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "company.ai_updated"))
    assert event is not None and event.tenant_id == tenant.id
    assert event.details and "extraction_api_key" in event.details["fields"]
    assert "company-key" not in str(event.details)


async def test_a_saved_key_is_kept_but_never_sent_to_another_provider(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    _, headers = await _admin(client, db)
    await client.put("/company/ai", json=OWN, headers=headers)
    same = {**OWN, "extraction": {**OWN["extraction"], "api_key": None, "effort": "low"}}
    moved = {**OWN, "extraction": {"provider": "openai", "model": "gpt-6.1-terra"}}

    kept = await client.put("/company/ai", json=same, headers=headers)
    refused = await client.put("/company/ai", json=moved, headers=headers)

    assert kept.status_code == 200 and kept.json()["extraction"]["api_key"]["hint"] == "…1234"
    assert refused.status_code == 400 and "new provider" in refused.json()["detail"]


async def test_a_first_save_needs_a_key_and_voice_notes_can_be_turned_off(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    tenant, headers = await _admin(client, db)
    no_key = {"extraction": {"provider": "anthropic", "model": "claude-sonnet-5"}}

    assert (await client.put("/company/ai", json=no_key, headers=headers)).status_code == 400
    await client.put("/company/ai", json=OWN, headers=headers)
    off = await client.put("/company/ai", json={"extraction": {**OWN["extraction"], "api_key": None}}, headers=headers)

    assert off.status_code == 200 and off.json()["transcription"]["configured"] is False
    keys = set(await db.scalars(select(CompanySetting.key).where(CompanySetting.tenant_id == tenant.id)))
    assert not {k for k in keys if k.startswith("transcription_")}


async def test_a_url_cannot_be_sent(client: AsyncClient, db: AsyncSession, own_ai_keys: None) -> None:
    _, headers = await _admin(client, db)
    typed = {"extraction": {"provider": "openai_compatible", "model": "m", "api_key": "k" * 12,
                            "base_url": "http://gotenberg:3000"}}

    assert (await client.put("/company/ai", json=typed, headers=headers)).status_code == 422


async def test_only_the_admin_of_a_hosted_company_reaches_it(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, admin = await _admin(client, db)
    for role in ("approver", "viewer", "technician"):
        member = await _headers(client, await _member(db, tenant, role))
        assert (await client.get("/company/ai", headers=member)).status_code == 403, role
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)  # an installation's AI is /instance/ai
    assert (await client.get("/company/ai", headers=admin)).status_code == 404


async def test_a_company_on_the_platforms_ai_sees_nothing_of_it_and_has_nothing_to_set(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    _, headers = await _admin(client, db, platform_ai=True)

    shown = await client.get("/company/ai", headers=headers)
    refused = await client.put("/company/ai", json=OWN, headers=headers)

    assert shown.json()["platform_ai"] is True and shown.json()["extraction"]["api_key"]["is_set"] is False
    assert "PLATFORM" not in shown.text and "claude" not in shown.json()["extraction"]["model"]
    assert refused.status_code == 400


async def test_each_company_reads_only_its_own_settings(client: AsyncClient, db: AsyncSession, own_ai_keys: None) -> None:
    _, acme = await _admin(client, db)
    _, other = await _admin(client, db)
    await client.put("/company/ai", json=OWN, headers=acme)

    seen = await client.get("/company/ai", headers=other)

    assert seen.json()["extraction"]["configured"] is False and "1234" not in seen.text


async def test_the_test_button_tries_the_company_key_at_the_providers_address_and_is_limited(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, headers = await _admin(client, db)
    await client.put("/company/ai", json=OWN, headers=headers)
    tried: list[AIConfig] = []

    async def fake_check(config: AIConfig) -> None:
        tried.append(config)

    monkeypatch.setattr(company_ai_api, "check_ai", fake_check)
    monkeypatch.setattr(company_ai_api.rate_limit.ai_check_by_tenant, "max_attempts", 2)
    switch = {"extraction": {"provider": "openai", "model": "gpt-6.1-terra", "api_key": "sk-proj-typed-key-9"}}

    ok = await client.post("/company/ai/check", json={"extraction": {**OWN["extraction"], "api_key": None}}, headers=headers)
    typed = await client.post("/company/ai/check", json=switch, headers=headers)
    limited = await client.post("/company/ai/check", json=switch, headers=headers)

    assert ok.json() == {"ok": True, "reason": None, "detail": None}
    assert typed.json()["ok"] is True and limited.status_code == 429
    assert tried[0].api_key == "sk-ant-company-key-1234" and tried[0].base_url == ""
    assert tried[1].base_url == "https://api.openai.com/v1" and not tried[1].platform_paid
    # A form with nothing to try is refused before it counts, even with the limit used up.
    assert (await client.post("/company/ai/check", json={}, headers=headers)).status_code == 400


# ── Admission and the first steps ────────────────────────────────────────────────────────


async def test_a_company_without_its_ai_cannot_start_a_report_until_it_enters_it(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    tenant, headers = await _admin(client, db)

    assert await plans.new_report_refusal(db, tenant) == "not_configured"
    assert await plans.message_refusal(db, tenant, voice=True) == "voice_not_configured"
    assert (await client.get("/dashboard", headers=headers)).json()["checklist"]["ai"] is False

    await client.put("/company/ai", json=OWN, headers=headers)
    await db.refresh(tenant)

    assert await plans.new_report_refusal(db, tenant) is None
    assert await plans.message_refusal(db, tenant, voice=True) is None
    checklist = (await client.get("/dashboard", headers=headers)).json()["checklist"]
    assert checklist["ai"] and checklist["transcription"]


async def test_the_app_refuses_a_capture_from_a_company_without_its_ai(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None
) -> None:
    tenant, _ = await _admin(client, db)
    technician = await _member(db, tenant, "technician")
    doc_type = DocumentType(tenant_id=tenant.id, name="Visita", field_schema={}, is_active=True)
    db.add(doc_type)
    await db.flush()
    db.add(DocumentTemplate(tenant_id=tenant.id, document_type_id=doc_type.id, file_path="x.docx", version=1, is_active=True))
    await db.commit()

    refused = await client.post(
        "/capture", data={"document_type_id": str(doc_type.id), "text": "Visita"},
        headers=await _headers(client, technician) | {"Idempotency-Key": str(uuid.uuid4())},
    )

    assert refused.status_code == 402


# ── Who pays ─────────────────────────────────────────────────────────────────────────────


async def test_calls_made_with_a_companys_key_are_logged_as_its_own_and_left_out_of_the_breaker(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await _company(db)
    own = usage_of(llm.LLMResult({}, 1_000_000, 0, "claude-sonnet-5", platform_paid=False))
    platform = ToolUsage(model_used="claude-sonnet-5", cost_usd=0.5)
    await write_execution_log(tenant_id=tenant.id, report_id=None, step="extract", status="success", usage=own)
    await write_execution_log(tenant_id=tenant.id, report_id=None, step="extract", status="success", usage=platform)
    since = datetime.now(UTC) - timedelta(hours=1)

    flags = sorted(await db.scalars(select(ExecutionLog.platform_key).where(ExecutionLog.tenant_id == tenant.id)))
    spent = await ExecutionLogRepository(db).total_cost_since(since)
    company_spent = await ExecutionLogRepository(db).total_cost_since(since, tenant_id=tenant.id)

    assert flags == [False, True] and own.cost_usd == pytest.approx(2.0)
    assert spent == pytest.approx(0.5) and company_spent == pytest.approx(0.5)
    monkeypatch.setattr(settings, "DAILY_SPEND_CAP_USD", 1.0)
    assert await plans.message_refusal(db, tenant, voice=False) is None  # its own 2 USD don't stop it


# ── A key the provider refuses ───────────────────────────────────────────────────────────


async def test_a_refused_key_ends_the_report_at_once_with_its_own_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def refusing(api_key: str) -> object:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=request), body=None)

    monkeypatch.setattr(llm, "_anthropic_client", refusing)
    config = AIConfig(provider="anthropic", model="claude-sonnet-5", api_key="sk-ant-wrong-key", base_url="", effort="")

    with pytest.raises(ProviderRejectedKeyError) as refused:
        await llm.structured_completion(system="s", user="u", model_cls=ToolUsage, tool_name="t", config=config)
    with pytest.raises(CheckFailed) as checked:
        await check_ai(config)

    assert isinstance(refused.value, PermanentJobError) and refused.value.reason_key == "ai_key_rejected"
    assert checked.value.reason == "auth"


# ── The super admin, and a company's end ─────────────────────────────────────────────────


async def test_the_super_admin_moves_a_company_onto_the_platforms_ai(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _company(db)
    root = TenantUser(email=f"root-{uuid.uuid4().hex[:6]}@r.test", hashed_password=hash_password(PASSWORD),
                      full_name="Root", role="super_admin", is_active=True)
    db.add(root)
    await db.commit()

    changed = await client.patch(f"/admin/tenants/{tenant.id}", json={"platform_ai": True}, headers=await _headers(client, root))

    assert changed.status_code == 200 and changed.json()["platform_ai"] is True
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "tenant.platform_ai_changed"))
    assert event is not None and event.details == {"platform_ai": {"from": False, "to": True}}


async def test_a_companys_keys_leave_with_it_and_never_in_its_export(
    db: AsyncSession, own_ai_keys: None
) -> None:
    tenant = await _company(db)
    await company_ai.save(db, tenant.id, {"extraction_provider": "anthropic", "extraction_api_key": "sk-ant-leaving-key-77"})
    await db.commit()

    archive = await export.build(db, tenant, datetime.now(UTC))
    try:
        import zipfile

        with zipfile.ZipFile(archive) as zipped:
            assert not any(b"leaving-key" in zipped.read(name) for name in zipped.namelist())
    finally:
        archive.unlink()
    await data_lifecycle.purge_tenant(db, tenant)
    await db.commit()

    assert await db.scalar(select(func.count()).select_from(CompanySetting)) == 0


async def test_reasoning_effort_goes_only_to_the_provider_that_needs_it(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, object]] = []

    class Completions:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            sent.append(kwargs)
            call = SimpleNamespace(type="function", function=SimpleNamespace(arguments='{"ok": true}'))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))], usage=None)

    monkeypatch.setattr(llm, "_openai_client", lambda *_: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))

    class Ping(BaseModel):
        ok: bool

    openai_config = company_ai.extraction_from({"extraction_provider": "openai", "extraction_api_key": "sk-proj-" + "x" * 8})
    # An installation configured from its .env, effort included: a self-hosted OpenAI-compatible
    # server may refuse a field it doesn't know.
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "EXTRACTION_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setattr(settings, "EXTRACTION_API_KEY", "local-key")
    monkeypatch.setattr(settings, "EXTRACTION_EFFORT", "low")
    other = instance_settings.ai_from({})
    for config in (openai_config, other):
        await llm.structured_completion(system="s", user="u", model_cls=Ping, tool_name="t", config=config)

    assert sent[0]["reasoning_effort"] == "none" and "reasoning_effort" not in sent[1]


# ── The invariants end to end: whose key a real call uses, who pays, what the sender hears ─


def _anthropic_answer(used: list[str], data: str = '{"fields": {"summary": "todo bien"}, "evidence": {}}') -> object:
    def client(api_key: str) -> SimpleNamespace:
        used.append(api_key)

        async def create(**_: object) -> SimpleNamespace:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=data)], stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
            )

        return SimpleNamespace(messages=SimpleNamespace(create=create))

    return client


async def test_a_companys_report_runs_on_its_own_key_and_is_logged_as_its_own(
    db: AsyncSession, own_ai_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await _company(db)
    await company_ai.save(db, tenant.id, {"extraction_provider": "anthropic", "extraction_api_key": "sk-ant-company-run-key"})
    report = Report(tenant_id=tenant.id, status="pending", requester_channel="web", requester_identifier="tecnica")
    db.add(report)
    await db.commit()
    used: list[str] = []
    monkeypatch.setattr(llm, "_anthropic_client", _anthropic_answer(used))
    state = AgentState(
        thread_id=str(report.id), tenant_id=tenant.id, channel_connection_id=uuid.uuid4(), channel_type="web",
        sender_id="tecnica", report_id=report.id, raw_payload={}, incoming_text="Visita: todo bien",
        document_type_name="Visita", field_schema={"summary": {"type": "str", "description": "Resumen", "required": True}},
    )

    await extract_node(state)

    assert used == ["sk-ant-company-run-key"]
    log = await db.scalar(select(ExecutionLog).where(ExecutionLog.report_id == report.id, ExecutionLog.step == "extract"))
    assert log is not None and log.platform_key is False and float(log.cost_usd or 0) > 0


async def test_a_transcription_says_whose_key_paid_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    async def create(**_: object) -> SimpleNamespace:
        return SimpleNamespace(text="hola", duration=12.0)

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(transcription, "_client", lambda *_: client)
    own = company_ai.transcription_from({"transcription_provider": "groq", "transcription_api_key": "gsk_" + "x" * 10})

    result = await transcription.transcribe(b"opus", "a.ogg", "es", config=own)

    assert result.platform_paid is False and transcription_usage(result).platform_key is False


async def test_a_refused_key_is_not_retried_and_tells_the_sender_why(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refused(job: ClaimedJob, _worker_id: str) -> None:
        raise ProviderRejectedKeyError("The AI provider refused the key (AuthenticationError)")

    retried: list[bool] = []
    told: list[str] = []

    async def fail_or_retry(job: ClaimedJob, worker_id: str, error: str, *, retryable: bool) -> FailOutcome:
        retried.append(retryable)
        return "failed"

    monkeypatch.setattr(runner, "execute", refused)
    monkeypatch.setattr(runner, "fail_or_retry", fail_or_retry)
    monkeypatch.setattr(runner, "give_up", AsyncMock(side_effect=lambda report_id, error, reason="failure": told.append(reason)))
    monkeypatch.setattr(runner, "extend_lease", AsyncMock(return_value=True))

    await runner.process(ClaimedJob(uuid.uuid4(), uuid.uuid4(), "run", {}, 1, 3), "worker-1")

    assert retried == [False] and told == ["ai_key_rejected"]


async def test_the_platforms_budget_stops_only_the_companies_it_pays_for(
    db: AsyncSession, own_ai_keys: None, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_platform = await _company(db, platform_ai=True)
    own = await _company(db, name="Own")
    await write_execution_log(
        tenant_id=on_platform.id, report_id=None, step="extract", status="success",
        usage=ToolUsage(model_used="claude-sonnet-5", cost_usd=5.0),
    )
    monkeypatch.setattr(settings, "DAILY_SPEND_CAP_USD", 3.0)

    assert await plans.message_refusal(db, on_platform, voice=False) == "spend_capped"
    assert await plans.message_refusal(db, own, voice=False) is None


async def test_the_template_assistant_says_the_key_was_refused_instead_of_failing(
    client: AsyncClient, db: AsyncSession, own_ai_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant, headers = await _admin(client, db)
    await client.put("/company/ai", json=OWN, headers=headers)
    doc_type = DocumentType(tenant_id=tenant.id, name="Parte", field_schema={}, is_active=True)
    db.add(doc_type)
    await db.commit()

    async def refused(**_: object) -> None:
        raise ProviderRejectedKeyError("refused")

    monkeypatch.setattr(template_assistant_api.assistant, "create_draft", refused)
    response = await client.post(
        f"/document-types/{doc_type.id}/template-assistant", headers=headers,
        files={"file": ("parte.docx", b"PK-not-really", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 400 and "refused your company's key" in response.json()["detail"]


class _Asked(Exception):
    """Ends a call right after it asked the AI: what matters here is with which settings."""


_COMPANY_AI = AIConfig(provider="anthropic", model="m", api_key="sk-ant-COMPANY", base_url="", effort="", platform_paid=False)
_COMPANY_VOICE = TranscriptionConfig(base_url="https://api.groq.com/openai/v1", api_key="gsk_COMPANY", model="w", platform_paid=False)


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch, own_ai_keys: None, tmp_path: Path) -> dict[str, list[object]]:
    seen: dict[str, list[object]] = {"companies": [], "settings": []}

    async def extraction_for(tenant_id: uuid.UUID) -> AIConfig:
        seen["companies"].append(tenant_id)
        return _COMPANY_AI

    async def transcription_for(tenant_id: uuid.UUID) -> TranscriptionConfig:
        seen["companies"].append(tenant_id)
        return _COMPANY_VOICE

    async def ai(**kwargs: object) -> None:
        seen["settings"].append(kwargs["config"])
        raise _Asked

    async def voice(*_: object, config: TranscriptionConfig, **__: object) -> None:
        seen["settings"].append(config)
        raise _Asked

    monkeypatch.setattr(company_ai, "extraction_for", extraction_for)
    monkeypatch.setattr(company_ai, "transcription_for", transcription_for)
    for module in (doctype_node, intent_tool, template_assistant):
        monkeypatch.setattr(module, "structured_completion", ai)
    monkeypatch.setattr(transcription, "transcribe", voice)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    return seen


def _a_state(tenant_id: uuid.UUID, **values: Any) -> AgentState:
    return AgentState(
        thread_id="t", tenant_id=tenant_id, channel_connection_id=uuid.uuid4(), channel_type="telegram",
        sender_id="42", report_id=uuid.uuid4(), raw_payload={}, incoming_text="Revisión de la obra de la calle Mayor",
        **values,
    )


async def _choose_type(tenant_id: uuid.UUID, tmp_path: Path) -> object:
    types = [DocumentType(id=uuid.uuid4(), tenant_id=tenant_id, name=name, field_schema={}) for name in ("Visita", "Incidente")]
    return await doctype_node._classify_type(_a_state(tenant_id), types)


async def _classify(tenant_id: uuid.UUID, tmp_path: Path) -> object:
    return await intent_tool.classify_reply("la fecha era el martes, no el lunes", tenant_id)


async def _transcribe_note(tenant_id: uuid.UUID, tmp_path: Path) -> object:
    audio = tmp_path / "nota.ogg"
    audio.write_bytes(b"opus")
    return await media_node.transcribe_node.__wrapped__(_a_state(tenant_id, media_local_path=str(audio)))  # type: ignore[attr-defined]


async def _transcribe_reply(tenant_id: uuid.UUID, tmp_path: Path) -> object:
    adapter = SimpleNamespace(download_media=AsyncMock(return_value=b"opus"))
    job = ClaimedJob(uuid.uuid4(), uuid.uuid4(), "resume", {"media_reference": "file-id"}, 1, 3)
    with patch.object(runner, "get_channel_adapter", lambda _connection: adapter):
        return await runner._reply(job, SimpleNamespace(), Tenant(id=tenant_id, name="Acme", slug="acme", language="es"))  # type: ignore[arg-type]


async def _propose_template(tenant_id: uuid.UUID, tmp_path: Path) -> object:
    document = DocxDocument()
    document.add_paragraph("Cliente: Comunidad Calle Mayor 12")
    content = BytesIO()
    document.save(content)
    return await template_assistant.create_draft(
        tenant_id=tenant_id, document_type_id=uuid.uuid4(), filename="parte.docx", content=content.getvalue(), language="es"
    )


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (_choose_type, _COMPANY_AI),
        (_classify, _COMPANY_AI),
        (_transcribe_note, _COMPANY_VOICE),
        (_transcribe_reply, _COMPANY_VOICE),
        (_propose_template, _COMPANY_AI),
    ],
    ids=["document type", "reply intent", "voice note", "voice reply", "template assistant"],
)
async def test_every_ai_call_asks_for_its_companys_ai(
    asked: dict[str, list[object]], tmp_path: Path, call: Callable[[uuid.UUID, Path], Awaitable[object]], expected: object
) -> None:
    tenant_id = uuid.uuid4()

    with contextlib.suppress(_Asked):  # the reply classifier turns any failure into a correction
        await call(tenant_id, tmp_path)

    assert asked["companies"] == [tenant_id] and asked["settings"] == [expected]
