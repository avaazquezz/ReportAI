"""A pause is a normal graph return carrying '__interrupt__'; the report row has to say what it is
waiting for, or the reply that answers it would start a brand-new run (and a second extraction)."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent.nodes.approval import human_approval_prompt_node
from app.services.agent.state import AgentState
from app.services.jobs.runner import _mark_paused_if_interrupted


async def _create_report(db: AsyncSession) -> Report:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    report = Report(tenant_id=tenant.id, status="pending", requester_channel="telegram", requester_identifier="12345")
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


def _interrupt(kind: str) -> dict[str, Any]:
    return {"__interrupt__": (SimpleNamespace(value={"kind": kind}),)}


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("confirm_report", "awaiting_approval"),
        ("select_document_type", "awaiting_doctype_selection"),  # 26 chars: also exercises String(30)
        ("missing_fields", "awaiting_details"),
    ],
)
async def test_each_kind_of_pause_is_recorded_on_the_report(
    db: AsyncSession, own_sessions: None, kind: str, status: str
) -> None:
    report = await _create_report(db)

    await _mark_paused_if_interrupted(_interrupt(kind), report.id)

    await db.refresh(report)
    assert report.status == status


async def test_a_run_that_finished_does_not_touch_the_status(db: AsyncSession, own_sessions: None) -> None:
    report = await _create_report(db)

    await _mark_paused_if_interrupted({}, report.id)
    await _mark_paused_if_interrupted(_interrupt("something_new"), report.id)  # unknown: don't guess

    await db.refresh(report)
    assert report.status == "pending"


async def test_approval_prompt_send_failure_does_not_raise(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, own_sessions: None
) -> None:
    """The 2026-08-13 finding: a failed prompt send must not kill the run before the
    interrupt — the already-paid-for extraction stays approvable from the admin panel."""
    report = await _create_report(db)
    monkeypatch.setattr(
        "app.services.agent.nodes.approval.send_on_origin_channel",
        AsyncMock(side_effect=RuntimeError("channel send failed")),
    )
    state = AgentState(
        thread_id=str(report.id),
        tenant_id=report.tenant_id,
        channel_connection_id=uuid.uuid4(),
        channel_type="telegram",
        sender_id="12345",
        report_id=report.id,
        raw_payload={},
        document_type_name="Meeting Minutes",
        field_schema={"summary": {"type": "str"}},
        extracted_fields={"summary": "Discussed Q3 budget"},
    )

    result = await human_approval_prompt_node.__wrapped__(state)

    assert result.extracted_fields == {"summary": "Discussed Q3 budget"}
