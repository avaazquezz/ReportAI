"""The tests that would have caught the dead resume branch: nothing ever wrote the
awaiting_* pause statuses, so find_pending_for_sender never matched and a reply
started a brand-new run (and a new extraction) instead of resuming the paused one."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent import invoke
from app.services.agent.nodes.approval import human_approval_prompt_node
from app.services.agent.state import AgentState
from app.services.observability import execution_log


async def _create_report(db: AsyncSession) -> Report:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    report = Report(
        tenant_id=tenant.id,
        status="pending",
        requester_channel="telegram",
        requester_identifier="12345",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


def _state_for(report: Report, **overrides: Any) -> AgentState:
    defaults: dict[str, Any] = {
        "thread_id": str(report.id),
        "tenant_id": report.tenant_id,
        "channel_connection_id": uuid.uuid4(),
        "channel_type": "telegram",
        "sender_id": "12345",
        "report_id": report.id,
        "raw_payload": {},
    }
    defaults.update(overrides)
    return AgentState(**defaults)


@pytest.fixture
def _patch_sessions(monkeypatch: pytest.MonkeyPatch, _test_engine) -> None:
    """Point the own-session factories used by invoke and the observability decorator
    at the test database instead of the app database."""
    test_sessions = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(invoke, "AsyncSessionLocal", test_sessions)
    monkeypatch.setattr(execution_log, "AsyncSessionLocal", test_sessions)


def _graph_returning(result: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(ainvoke=AsyncMock(return_value=result))


async def test_run_graph_marks_awaiting_approval_on_interrupt(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _patch_sessions: None
) -> None:
    report = await _create_report(db)
    graph = _graph_returning(
        {"__interrupt__": (SimpleNamespace(value={"kind": "confirm_report"}),)}
    )
    monkeypatch.setattr(invoke, "get_compiled_graph", lambda: graph)

    await invoke._run_graph(_state_for(report))

    await db.refresh(report)
    assert report.status == "awaiting_approval"


async def test_run_graph_marks_awaiting_doctype_selection_on_interrupt(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _patch_sessions: None
) -> None:
    # "awaiting_doctype_selection" is 26 chars — also exercises the String(30) column.
    report = await _create_report(db)
    graph = _graph_returning(
        {"__interrupt__": (SimpleNamespace(value={"kind": "select_document_type"}),)}
    )
    monkeypatch.setattr(invoke, "get_compiled_graph", lambda: graph)

    await invoke._run_graph(_state_for(report))

    await db.refresh(report)
    assert report.status == "awaiting_doctype_selection"


async def test_completed_run_does_not_touch_status(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _patch_sessions: None
) -> None:
    report = await _create_report(db)
    monkeypatch.setattr(invoke, "get_compiled_graph", lambda: _graph_returning({}))

    await invoke._run_graph(_state_for(report))

    await db.refresh(report)
    assert report.status == "pending"


async def test_resume_graph_remarks_pause_on_reinterrupt(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _patch_sessions: None
) -> None:
    """A correction reply re-extracts and pauses again — the resume path must re-mark
    the pause status the claim had just flipped back to 'pending'."""
    report = await _create_report(db)
    graph = _graph_returning(
        {"__interrupt__": (SimpleNamespace(value={"kind": "confirm_report"}),)}
    )
    monkeypatch.setattr(invoke, "get_compiled_graph", lambda: graph)

    await invoke._resume_graph(str(report.id), "the date is wrong, it was Tuesday")

    await db.refresh(report)
    assert report.status == "awaiting_approval"


async def test_approval_prompt_send_failure_does_not_raise(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _patch_sessions: None
) -> None:
    """The 2026-08-13 finding: a failed prompt send must not kill the run before the
    interrupt — the already-paid-for extraction stays approvable from the admin panel."""
    report = await _create_report(db)
    monkeypatch.setattr(
        "app.services.agent.nodes.approval.send_on_origin_channel",
        AsyncMock(side_effect=RuntimeError("channel send failed")),
    )
    state = _state_for(
        report,
        document_type_name="Meeting Minutes",
        extracted_fields={"summary": "Discussed Q3 budget"},
    )

    result = await human_approval_prompt_node(state)

    assert result.extracted_fields == {"summary": "Discussed Q3 budget"}
