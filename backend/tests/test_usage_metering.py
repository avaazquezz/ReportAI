"""Every AI call is metered per tenant in execution_logs: tokens and cost for each LLM call,
audio seconds and cost for each transcription — what quotas and spend caps will count."""

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document_type import DocumentType
from app.models.execution_log import ExecutionLog
from app.models.report import Report
from app.models.tenant import Tenant
from app.services import transcription
from app.services.agent.nodes import approval, doctype, extract, media
from app.services.agent.state import AgentState
from app.services.agent.tools.pricing import estimate_transcription_cost_usd
from app.services.llm import LLMResult

SCHEMA = {"summary": {"type": "str", "description": "What happened", "required": True}}


async def _report(db: AsyncSession) -> Report:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    report = Report(tenant_id=tenant.id, status="pending", requester_channel="telegram", requester_identifier="42")
    db.add(report)
    await db.commit()
    return report


def _state(report: Report, **overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "thread_id": str(report.id), "tenant_id": report.tenant_id, "channel_connection_id": uuid.uuid4(),
        "channel_type": "telegram", "sender_id": "42", "report_id": report.id, "raw_payload": {},
        "incoming_text": "Visited the site, all good", "document_type_name": "Visit", "field_schema": SCHEMA,
    }
    values.update(overrides)
    return AgentState(**values)


async def _rows(db: AsyncSession) -> dict[str, ExecutionLog]:
    return {row.step: row for row in (await db.execute(select(ExecutionLog))).scalars()}


def _transcription_client(monkeypatch: pytest.MonkeyPatch, model: str, answer: SimpleNamespace) -> AsyncMock:
    create = AsyncMock(return_value=answer)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    monkeypatch.setattr(transcription, "_client", lambda *_: client)
    monkeypatch.setattr(settings, "TRANSCRIPTION_API_KEY", "gsk-test")
    monkeypatch.setattr(settings, "TRANSCRIPTION_MODEL", model)
    return create


@pytest.mark.parametrize(("model", "cost"), [("claude-sonnet-5", 1200 * 2 / 1e6 + 300 * 10 / 1e6), ("deepseek-chat", None)])
async def test_an_extraction_logs_its_tokens_and_cost(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, model: str, cost: float | None
) -> None:
    report = await _report(db)
    answer = LLMResult({"fields": {"summary": "all good"}, "evidence": {}}, 1200, 300, model)
    monkeypatch.setattr(extract, "structured_completion", AsyncMock(return_value=answer))

    await extract.extract_node(_state(report))

    row = (await _rows(db))["extract"]
    assert (row.model_used, row.input_tokens, row.output_tokens) == (model, 1200, 300)
    if cost is None:
        assert row.cost_usd is None  # unpriced: the tokens are still there to count
    else:
        assert float(row.cost_usd or 0) == pytest.approx(cost)


async def test_the_document_type_choice_and_the_reply_classifier_log_their_tokens(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = await _report(db)
    db.add_all([
        DocumentType(tenant_id=report.tenant_id, name="Acta de reunión", field_schema=SCHEMA, is_active=True),
        DocumentType(tenant_id=report.tenant_id, name="Visita de obra", field_schema=SCHEMA, is_active=True),
    ])
    await db.commit()
    choice = LLMResult({"type_number": 2, "confidence": 0.9}, 60, 4, "claude-sonnet-5")
    monkeypatch.setattr(doctype, "structured_completion", AsyncMock(return_value=choice))
    monkeypatch.setattr(approval, "classify_reply", AsyncMock(return_value=("correct", LLMResult({}, 40, 3, "claude-haiku-4-5"))))

    await doctype.resolve_tenant_doctype_node(_state(report, document_type_name=None, field_schema=None, source_text="Visité la obra"))
    await approval.classify_approval_reply_node(_state(report, pending_user_reply="la fecha era el martes"))

    rows = await _rows(db)
    doctype_row, reply_row = rows["resolve_tenant_doctype"], rows["classify_approval_reply"]
    assert (doctype_row.input_tokens, doctype_row.output_tokens) == (60, 4)
    assert float(doctype_row.cost_usd or 0) == pytest.approx(60 * 2 / 1e6 + 4 * 10 / 1e6)
    assert (reply_row.model_used, reply_row.input_tokens, reply_row.output_tokens) == ("claude-haiku-4-5", 40, 3)
    assert float(reply_row.cost_usd or 0) == pytest.approx(40 * 1 / 1e6 + 3 * 5 / 1e6)


async def test_a_transcription_logs_the_audio_seconds_and_their_cost(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = await _report(db)
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"opus")
    create = _transcription_client(monkeypatch, "whisper-large-v3-turbo", SimpleNamespace(text="hola", duration=42.5))

    await media.transcribe_node(_state(report, media_local_path=str(audio)))

    assert create.await_args.kwargs["response_format"] == "verbose_json"  # where whisper reports the length
    row = (await _rows(db))["transcribe"]
    assert (row.model_used, float(row.audio_seconds or 0)) == ("whisper-large-v3-turbo", 42.5)
    assert float(row.cost_usd or 0) == pytest.approx(42.5 / 3600 * 0.04, abs=1e-6)
    assert row.input_tokens is None


async def test_a_model_without_verbose_json_is_asked_for_json_and_left_unpriced(monkeypatch: pytest.MonkeyPatch) -> None:
    create = _transcription_client(monkeypatch, "gpt-4o-mini-transcribe", SimpleNamespace(text="hola"))

    result = await transcription.transcribe(b"opus", "audio.ogg")

    assert create.await_args.kwargs["response_format"] == "json"  # the only format gpt-4o transcribe takes
    assert (result.text, result.seconds) == ("hola", None)


def test_transcription_prices_count_the_minimum_a_request_is_billed_for() -> None:
    assert estimate_transcription_cost_usd("whisper-large-v3-turbo", 3.0) == pytest.approx(10 / 3600 * 0.04)  # Groq: 10 s minimum
    assert estimate_transcription_cost_usd("whisper-large-v3", 3600.0) == pytest.approx(0.111)
    assert estimate_transcription_cost_usd("whisper-1", 60.0) == pytest.approx(0.006)
    assert estimate_transcription_cost_usd("gpt-4o-transcribe", 60.0) is None  # billed by the token
    assert estimate_transcription_cost_usd("whisper-large-v3-turbo", None) is None  # no length reported
