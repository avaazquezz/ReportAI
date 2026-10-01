"""IA-14 / IA-15 / IA-20: the AI provider is chosen per installation, extraction no longer
uses a forced tool_choice (a 400 on current Claude models), and a missing price can't
silently disable the spend cap."""

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.webhooks import email as email_webhook
from app.api.webhooks import whatsapp as whatsapp_webhook
from app.core.config import Settings, settings
from app.services import instance_settings, llm, transcription
from app.services.agent.nodes import extract, media
from app.services.agent.state import AgentState
from app.services.agent.tools.pricing import estimate_cost_usd, require_priced_model_for_spend_cap

_SCHEMA = {"summary": {"type": "str", "description": "What happened", "required": True}}


def _state(**overrides: Any) -> AgentState:
    import uuid

    defaults: dict[str, Any] = {
        "thread_id": "t",
        "tenant_id": uuid.uuid4(),
        "channel_connection_id": uuid.uuid4(),
        "channel_type": "telegram",
        "sender_id": "1",
        "report_id": uuid.uuid4(),
        "raw_payload": {},
        "incoming_text": "Visited the site, all good",
        "document_type_name": "Visit",
        "field_schema": _SCHEMA,
    }
    defaults.update(overrides)
    return AgentState(**defaults)


async def test_anthropic_extraction_uses_structured_output_not_forced_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps({"fields": {"summary": "all good"}, "evidence": {"summary": "Visited the site"}}))],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000),
        )
    )
    monkeypatch.setattr(llm, "_anthropic_client", lambda *_: SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "EXTRACTION_MODEL", "claude-sonnet-5-5")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")

    result = await extract.extract_node.__wrapped__(_state())

    kwargs = create.await_args.kwargs
    assert "tool_choice" not in kwargs  # forced tool_choice is a 400 on Sonnet 5.5 / Opus 5.5
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert result.extracted_fields == {"summary": "all good"}
    assert result.last_tool_usage is not None
    assert result.last_tool_usage.cost_usd == pytest.approx(12.0)  # $2 in + $10 out per MTok


async def test_openai_compatible_extraction_forces_the_function_and_logs_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                type="function",
                                function=SimpleNamespace(arguments=json.dumps({"fields": {"summary": "ok"}, "evidence": {}})),
                            )
                        ]
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_openai_client", lambda *_: client)
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "EXTRACTION_MODEL", "deepseek-chat")
    monkeypatch.setattr(settings, "EXTRACTION_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "EXTRACTION_API_KEY", "k")

    result = await extract.extract_node.__wrapped__(_state())

    kwargs = create.await_args.kwargs
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": extract.TOOL_NAME}}
    assert result.extracted_fields is not None
    assert result.extracted_fields == {"summary": "ok"}
    assert result.last_tool_usage is not None
    assert result.last_tool_usage.model_used == "deepseek-chat"
    assert result.last_tool_usage.cost_usd is None  # unpriced model: tokens only, no crash


async def test_openai_compatible_extraction_fails_loudly_when_the_model_skips_the_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None))], usage=None
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_openai_client", lambda *_: client)
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "EXTRACTION_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "EXTRACTION_API_KEY", "k")

    with pytest.raises(ValueError, match="did not call the extraction function"):
        await extract.extract_node.__wrapped__(_state())


def test_each_provider_needs_its_own_credentials_to_count_as_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "EXTRACTION_API_KEY", "EXTRACTION_BASE_URL"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "anthropic")
    assert not instance_settings.ai_from({}).configured
    assert instance_settings.ai_from({"extraction_api_key": "sk-ant"}).configured

    openai_style = {"extraction_provider": "openai_compatible", "extraction_api_key": "k"}
    assert not instance_settings.ai_from(openai_style).configured  # a base URL is needed too
    assert instance_settings.ai_from({**openai_style, "extraction_base_url": "https://api.deepseek.com"}).configured


async def test_an_unconfigured_installation_says_where_to_add_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "anthropic")

    with pytest.raises(instance_settings.NotConfiguredError, match="Settings → AI"):
        await extract.extract_node.__wrapped__(_state())


def test_the_server_starts_without_any_ai_key() -> None:
    # Keys can be entered in the panel's setup wizard: an installation must boot without them.
    Settings(_env_file=None, ANTHROPIC_API_KEY="", EXTRACTION_API_KEY="", TRANSCRIPTION_API_KEY="")


def test_channels_and_smtp_are_optional_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM_ADDRESS", "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN", "MAILGUN_API_KEY", "MAILGUN_SIGNING_KEY", "MAILGUN_INBOUND_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    minimal = Settings(_env_file=None)
    assert minimal.SMTP_HOST == "" and minimal.WHATSAPP_APP_SECRET == "" and minimal.MAILGUN_SIGNING_KEY == ""


def test_webhooks_reject_signatures_made_with_an_empty_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"entry": []}'
    forged = "sha256=" + hmac.new(b"", body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")
    assert whatsapp_webhook._verify_signature(body, forged) is False

    monkeypatch.setattr(settings, "MAILGUN_SIGNING_KEY", "")
    forged_mailgun = hmac.new(b"", b"1tok", hashlib.sha256).hexdigest()
    assert email_webhook._verify_signature("1", "tok", forged_mailgun) is False


async def test_transcription_goes_through_the_configured_openai_compatible_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, own_sessions: None
) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"fake-audio")
    create = AsyncMock(return_value=SimpleNamespace(text="hola mundo"))
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(transcription, "_client", lambda *_: client)
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "gsk-test")

    result = await media.transcribe_node.__wrapped__(_state(media_local_path=str(audio), language="en"))

    assert result.transcript == "hola mundo"
    assert create.await_args.kwargs["model"] == settings.TRANSCRIPTION_MODEL
    assert create.await_args.kwargs["language"] == "en"  # the company's language, not a fixed one
    assert result.last_tool_usage is not None and result.last_tool_usage.model_used == settings.TRANSCRIPTION_MODEL


async def test_transcription_without_a_key_explains_what_to_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="TRANSCRIPTION_API_KEY"):
        await transcription.transcribe(b"audio", "a.ogg")


def test_prices_match_anthropics_list_and_unknown_models_are_unpriced() -> None:
    assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert estimate_cost_usd("some-other-provider-model", 1, 1) is None


def test_spend_cap_refuses_to_run_blind() -> None:
    require_priced_model_for_spend_cap("claude-sonnet-5", 5.0)
    require_priced_model_for_spend_cap("deepseek-chat", 0.0)  # no cap, nothing to count
    with pytest.raises(RuntimeError, match="no price"):
        require_priced_model_for_spend_cap("deepseek-chat", 5.0)
