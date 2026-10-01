"""The dashboard: what waits on someone, what failed, and — for an admin — what is left to set up
before the first report."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.sender_invite import SenderInvite
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


async def _setup(client: AsyncClient, db: AsyncSession) -> tuple[Tenant, dict[str, str], dict[str, str]]:
    tenant = Tenant(name="Reformas García", slug=f"g-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    for email, role in (("admin@g.test", "tenant_admin"), ("viewer@g.test", "viewer")):
        db.add(TenantUser(tenant_id=tenant.id, email=email, hashed_password=hash_password("pw-12345678"), full_name=role, role=role, is_active=True))
    await db.commit()
    headers = []
    for email in ("admin@g.test", "viewer@g.test"):
        login = await client.post("/auth/login", json={"email": email, "password": "pw-12345678"})
        headers.append({"Authorization": f"Bearer {login.json()['access_token']}"})
    return tenant, headers[0], headers[1]


def _report(tenant: Tenant, status: str, *, days_ago: int = 0, sender: str = "42", connection: ChannelConnection | None = None) -> Report:
    return Report(
        tenant_id=tenant.id, status=status, requester_channel="telegram", requester_identifier=sender,
        channel_connection_id=connection.id if connection else None,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


@pytest.fixture(autouse=True)
def _closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALLOW_ANY_SENDER", False)


async def test_what_waits_and_what_failed(client: AsyncClient, db: AsyncSession) -> None:
    tenant, _, viewer = await _setup(client, db)
    connection = ChannelConnection(tenant_id=tenant.id, channel_type="telegram", display_name="Bot", credentials={"bot_token": "t"}, allowed_senders=["42"])
    db.add(connection)
    await db.flush()
    db.add(SenderInvite(tenant_id=tenant.id, connection_id=connection.id, label="Ana Ruiz", code_hash="x" * 64,
                        expires_at=datetime.now(UTC), used_at=datetime.now(UTC), sender_id="42"))
    delivered = _report(tenant, "delivered")
    db.add_all([
        _report(tenant, "awaiting_approval", connection=connection),
        _report(tenant, "awaiting_details", sender="43"),
        _report(tenant, "pending", sender="44"),
        _report(tenant, "failed", sender="45"),
        _report(tenant, "delivery_failed", sender="46"),
        _report(tenant, "failed", days_ago=30, sender="47"),  # old news
        delivered,
    ])
    await db.flush()
    db.add(Delivery(report_id=delivered.id, kind="email", destination="jefe@g.test", status="failed"))
    await db.commit()

    board = (await client.get("/dashboard", headers=viewer)).json()

    assert board["counts"] == {"waiting": 2, "processing": 1, "delivered_recently": 1, "failed_recently": 2, "failed_copies_recently": 1}
    assert {r["requester"] for r in board["waiting"]} == {"Ana Ruiz", "43"}  # named when invited
    assert {r["status"] for r in board["failed"]} == {"failed", "delivery_failed"}
    assert board["checklist"] is None  # not an admin


async def test_the_admin_sees_what_is_left_to_set_up(client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "TRANSCRIPTION_API_KEY", "GROQ_API_KEY", "SMTP_HOST"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "EXTRACTION_PROVIDER", "anthropic")
    tenant, admin, _ = await _setup(client, db)

    empty = (await client.get("/dashboard", headers=admin)).json()["checklist"]
    assert not any(empty.values())

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant")
    connection = ChannelConnection(tenant_id=tenant.id, channel_type="telegram", display_name="Bot", credentials={"bot_token": "t"}, allowed_senders=["42"])
    doc_type = DocumentType(tenant_id=tenant.id, name="Parte", field_schema={})
    db.add_all([connection, doc_type])
    await db.flush()
    db.add_all([
        DocumentTemplate(tenant_id=tenant.id, document_type_id=doc_type.id, file_path="x.docx", version=1, is_active=True),
        _report(tenant, "delivered"),
    ])
    await db.commit()

    done = (await client.get("/dashboard", headers=admin)).json()["checklist"]
    assert done == {"ai": True, "transcription": False, "email": False, "channel": True, "senders": True, "document_type": True, "first_report": True}
