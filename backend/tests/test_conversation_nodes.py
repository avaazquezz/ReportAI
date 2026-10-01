"""The conversation the bot has around a report: recap with buttons, what a reply means, asking
for what is missing, ending on purpose. Nodes are called directly; the channel is a recorder."""

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.job import Job
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent.nodes import approval, completeness, doctype, lifecycle
from app.services.agent.state import AgentState, DocumentTypeOption
from app.services.llm import LLMResult

SCHEMA = {
    "visit_date": {"type": "date", "label": "Fecha", "required": True},
    "summary": {"type": "str", "required": True},
    "contact": {"type": "str", "required": False},
}


class Sent:
    """Records what a node told the person."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, list[Any] | None]] = []

    async def __call__(self, state: AgentState, text: str, *, buttons: list[Any] | None = None) -> None:
        self.messages.append((text, buttons))


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Sent:
    recorder = Sent()
    for module in (approval, completeness, lifecycle, doctype):
        monkeypatch.setattr(module, "send_on_origin_channel", recorder)
    return recorder


async def _world(db: AsyncSession, *, status: str = "awaiting_approval") -> tuple[Report, ChannelConnection]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    connection = ChannelConnection(
        tenant_id=tenant.id, channel_type="telegram", display_name="Bot",
        credentials={"bot_token": "t"}, allowed_senders=[], is_active=True,
    )
    db.add(connection)
    await db.flush()
    report = Report(
        tenant_id=tenant.id, status=status, requester_channel="telegram", requester_identifier="42",
        channel_connection_id=connection.id,
    )
    db.add(report)
    await db.commit()
    return report, connection


def _state(report: Report, connection: ChannelConnection, **overrides: Any) -> AgentState:
    values: dict[str, Any] = {
        "thread_id": str(report.id), "tenant_id": report.tenant_id, "channel_connection_id": connection.id,
        "channel_type": "telegram", "sender_id": "42", "report_id": report.id, "raw_payload": {},
        "document_type_name": "Visita", "field_schema": SCHEMA,
        "extracted_fields": {"visit_date": "2026-08-18", "summary": "Todo bien", "contact": None},
        "evidence": {"summary": {"quote": "todo bien", "verified": True}, "visit_date": {"quote": "18 de agosto", "verified": True}},
    }
    values.update(overrides)
    return AgentState(**values)


async def test_the_recap_offers_three_buttons_and_is_saved_for_the_panel(
    db: AsyncSession, own_sessions: None, sent: Sent
) -> None:
    report, connection = await _world(db)

    await approval.human_approval_prompt_node.__wrapped__(_state(report, connection, source_text="Visité la obra"))

    text, buttons = sent.messages[-1]
    assert "Fecha: 18/08/2026" in text and "Confirma" in text
    assert [b.action for b in buttons or []] == ["confirm", "correct", "cancel"]
    await db.refresh(report)
    assert report.extracted_fields == {"visit_date": "2026-08-18", "summary": "Todo bien", "contact": None}
    assert report.source_text == "Visité la obra" and report.evidence["summary"]["quote"] == "todo bien"


async def test_a_long_recap_is_split_and_the_buttons_go_on_the_last_part(
    db: AsyncSession, own_sessions: None, sent: Sent
) -> None:
    report, connection = await _world(db)
    state = _state(report, connection, extracted_fields={"visit_date": "2026-08-18", "summary": "x" * 9000, "contact": None})

    await approval.human_approval_prompt_node.__wrapped__(state)

    assert len(sent.messages) > 1
    assert all(buttons is None for _, buttons in sent.messages[:-1]) and sent.messages[-1][1]


async def test_a_pressed_confirm_or_cancel_button_is_taken_at_its_word(
    db: AsyncSession, own_sessions: None
) -> None:
    report, connection = await _world(db)
    confirm = await approval.classify_approval_reply_node.__wrapped__(_state(report, connection, pending_user_reply={"action": "confirm"}))
    cancel = await approval.classify_approval_reply_node.__wrapped__(_state(report, connection, pending_user_reply={"action": "cancel"}))
    assert (confirm.intent, cancel.intent) == ("confirm", "cancel")


async def test_a_short_yes_confirms_without_asking_the_model(db: AsyncSession, own_sessions: None) -> None:
    report, connection = await _world(db)

    result = await approval.classify_approval_reply_node.__wrapped__(_state(report, connection, pending_user_reply="Sí."))

    assert result.intent == "confirm" and result.correction_text is None and result.last_tool_usage is None


async def test_a_correction_is_counted_and_carried_to_the_next_extraction(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, connection = await _world(db)
    monkeypatch.setattr(approval, "classify_reply", AsyncMock(return_value=("correct", LLMResult({}, 40, 3, "claude-sonnet-5"))))

    result = await approval.classify_approval_reply_node.__wrapped__(
        _state(report, connection, pending_user_reply="la fecha era el martes")
    )

    assert (result.intent, result.correction_text, result.correction_attempts) == ("correct", "la fecha era el martes", 1)
    assert result.last_tool_usage is not None and result.last_tool_usage.model_used


async def test_edits_from_the_panel_replace_the_fields_and_drop_their_stale_evidence(
    db: AsyncSession, own_sessions: None
) -> None:
    report, connection = await _world(db)
    reply = {"action": "confirm", "fields": {"visit_date": "2026-08-19"}}

    result = await approval.classify_approval_reply_node.__wrapped__(_state(report, connection, pending_user_reply=reply))

    assert result.intent == "confirm"
    assert result.extracted_fields is not None and result.extracted_fields["visit_date"] == "2026-08-19"
    assert "visit_date" not in result.evidence and "summary" in result.evidence


async def test_panel_edits_that_do_not_fit_are_sent_back_instead_of_approved(
    db: AsyncSession, own_sessions: None
) -> None:
    report, connection = await _world(db)
    reply = {"action": "confirm", "fields": {"visit_date": "mañana"}}

    result = await approval.classify_approval_reply_node.__wrapped__(_state(report, connection, pending_user_reply=reply))

    assert result.intent == "ask" and result.last_validation_error


async def test_the_bot_says_what_is_missing_by_label_and_counts_the_ask(
    db: AsyncSession, own_sessions: None, sent: Sent
) -> None:
    report, connection = await _world(db)
    state = _state(report, connection, missing_fields=["visit_date"], extracted_fields={"visit_date": None, "summary": "x"})

    result = await completeness.ask_missing_fields_node.__wrapped__(state)

    assert "• Fecha" in sent.messages[0][0] and result.missing_attempts == 1


async def test_the_answer_to_a_missing_field_question_becomes_a_correction(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, connection = await _world(db)
    for reply in ("fue el martes", {"text": "fue el martes"}):
        monkeypatch.setattr(completeness, "interrupt", lambda _payload, reply=reply: reply)
        result = await completeness.await_missing_fields_node.__wrapped__(_state(report, connection))
        assert result.correction_text == "fue el martes"


async def test_the_completeness_check_lists_only_required_gaps(db: AsyncSession, own_sessions: None) -> None:
    report, connection = await _world(db)
    state = _state(report, connection, extracted_fields={"visit_date": None, "summary": "x", "contact": None})

    result = await completeness.check_completeness_node.__wrapped__(state)

    assert result.missing_fields == ["visit_date"]  # `contact` is optional


async def test_cancelling_closes_the_report_and_says_so(db: AsyncSession, own_sessions: None, sent: Sent) -> None:
    report, connection = await _world(db)

    await lifecycle.cancel_report_node.__wrapped__(_state(report, connection))

    await db.refresh(report)
    assert report.status == "cancelled" and report.completed_at is not None
    assert sent.messages[-1][0] == "Informe cancelado."


async def test_a_reply_that_starts_another_report_replaces_the_old_one(
    db: AsyncSession, own_sessions: None, sent: Sent
) -> None:
    report, connection = await _world(db)

    await lifecycle.supersede_report_node.__wrapped__(
        _state(report, connection, pending_user_reply="Ahora la visita de Valencia")
    )

    await db.refresh(report)
    assert report.status == "cancelled"
    reports = (await db.execute(select(Report).where(Report.id != report.id))).scalars().all()
    assert len(reports) == 1 and reports[0].status == "pending"
    [job] = (await db.execute(select(Job).where(Job.report_id == reports[0].id))).scalars().all()
    assert (job.kind, job.payload["text"]) == ("run", "Ahora la visita de Valencia")


async def test_the_document_type_is_picked_when_the_model_is_confident(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.document_type import DocumentType

    report, connection = await _world(db)
    acta = DocumentType(tenant_id=report.tenant_id, name="Acta de reunión", field_schema=SCHEMA, is_active=True)
    visita = DocumentType(tenant_id=report.tenant_id, name="Visita de obra", field_schema=SCHEMA, is_active=True)
    db.add_all([acta, visita])
    await db.commit()
    monkeypatch.setattr(doctype, "structured_completion", AsyncMock(return_value=LLMResult({"type_number": 2, "confidence": 0.93}, 60, 4, "claude-sonnet-5")))
    state = _state(report, connection, document_type_id=None, document_type_name=None, field_schema=None, source_text="Visité la obra")

    result = await doctype.resolve_tenant_doctype_node.__wrapped__(state)

    chosen = {acta.id: "Acta de reunión", visita.id: "Visita de obra"}
    assert result.document_type_id is not None and chosen[result.document_type_id] == result.document_type_name
    assert result.last_tool_usage is not None


async def test_the_bot_asks_with_buttons_when_the_model_is_not_sure(
    db: AsyncSession, own_sessions: None, monkeypatch: pytest.MonkeyPatch, sent: Sent
) -> None:
    from app.models.document_type import DocumentType

    report, connection = await _world(db)
    db.add_all([
        DocumentType(tenant_id=report.tenant_id, name="Acta", field_schema=SCHEMA, is_active=True),
        DocumentType(tenant_id=report.tenant_id, name="Visita", field_schema=SCHEMA, is_active=True),
    ])
    await db.commit()
    monkeypatch.setattr(doctype, "structured_completion", AsyncMock(return_value=LLMResult({"type_number": 1, "confidence": 0.4}, 60, 4, "claude-sonnet-5")))
    state = _state(report, connection, document_type_id=None, field_schema=None, source_text="algo")

    resolved = await doctype.resolve_tenant_doctype_node.__wrapped__(state)
    assert resolved.document_type_id is None and len(resolved.available_document_types) == 2

    await doctype.send_document_type_prompt_node.__wrapped__(resolved)
    text, buttons = sent.messages[-1]
    assert "tipo de documento" in text and [b.action for b in buttons or []] == ["doctype", "doctype"]


async def test_a_pressed_document_type_button_selects_that_type(db: AsyncSession, own_sessions: None) -> None:
    from app.models.document_type import DocumentType

    report, connection = await _world(db)
    chosen = DocumentType(tenant_id=report.tenant_id, name="Visita", field_schema=SCHEMA, is_active=True)
    db.add(chosen)
    await db.commit()
    state = _state(
        report, connection, document_type_id=None,
        available_document_types=[DocumentTypeOption(id=chosen.id, name="Visita")],
        pending_user_reply={"action": "doctype", "arg": str(chosen.id)},
    )

    result = await doctype.parse_document_type_selection_node.__wrapped__(state)

    assert result.document_type_id == chosen.id
