"""IA-1: the pipeline used to finish without ever recording the PDF or the document type,
so the panel's history never offered the download. The tests that seeded reports inserted
file_path by hand, which is why nothing caught it."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.tenant import Tenant
from app.services.agent.nodes import deliver
from app.services.agent.state import AgentState
from app.services.observability import execution_log


async def test_finalize_records_pdf_path_and_document_type(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, _test_engine
) -> None:
    test_sessions = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(deliver, "AsyncSessionLocal", test_sessions)
    monkeypatch.setattr(execution_log, "AsyncSessionLocal", test_sessions)

    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    doc_type = DocumentType(tenant_id=tenant.id, name="Visit report", field_schema={})
    report = Report(
        tenant_id=tenant.id, status="pending", requester_channel="telegram", requester_identifier="1"
    )
    db.add_all([doc_type, report])
    await db.commit()

    state = AgentState(
        thread_id=str(report.id),
        tenant_id=tenant.id,
        channel_connection_id=uuid.uuid4(),
        channel_type="telegram",
        sender_id="1",
        report_id=report.id,
        raw_payload={},
        document_type_id=doc_type.id,
        rendered_pdf_path=f"storage/{report.id}/rendered.pdf",
    )

    await deliver.finalize_report_node(state)

    await db.refresh(report)
    assert report.status == "delivered"
    assert report.file_path == f"storage/{report.id}/rendered.pdf"
    assert report.document_type_id == doc_type.id
    assert report.completed_at is not None
