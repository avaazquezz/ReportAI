"""A company that asks to be deleted is blocked at once and, after its grace period, purged: no row,
file or paused conversation of it is left, and no other company loses anything. Voice notes,
temporary files and old delivery ids expire on their own."""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import Base
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.document_template import DocumentTemplate
from app.models.execution_log import ExecutionLog
from app.models.inbound_message import InboundMessage
from app.models.job import Job
from app.models.password_reset_token import PasswordResetToken
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.report_revision import ReportRevision
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import data_lifecycle
from tests.test_tenant_isolation import _auth, _company

PASSWORD = "x"  # what _company() gives everyone


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def forgotten_threads(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The checkpointer's deletions, each checked to happen while the report row still exists."""
    deleted: list[str] = []

    async def forget(thread_id: str) -> None:
        still_there = await db.scalar(select(func.count()).select_from(Report).where(Report.id == uuid.UUID(thread_id)))
        assert still_there, "checkpoints must go before the rows that lead to them"
        deleted.append(thread_id)

    monkeypatch.setattr(data_lifecycle, "get_checkpointer", lambda: SimpleNamespace(adelete_thread=forget))
    return deleted


def _put(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"data")
    return path


async def _full_company(db: AsyncSession, name: str, root: Path) -> dict[str, Any]:
    """One of every row a company can have, and one of every file it can leave on disk."""
    company = await _company(db, name)
    tenant, admin, ids = company["tenant"], company["admin"], company["ids"]
    report_id, tenant_id = ids["report_id"], tenant.id
    files = {
        "document": _put(root, f"{report_id}/rendered.pdf"),
        "audio": _put(root, f"{report_id}/audio.ogg"),
        "photo": _put(root, f"attachments/{tenant_id}/photo.jpg"),
        "template": _put(root, f"templates/{tenant_id}/template.docx"),
        "logo": _put(root, f"branding/{tenant_id}/logo.png"),
        "draft": _put(root, f"template_drafts/{tenant_id}/{uuid.uuid4()}/draft.docx"),
    }
    await db.execute(
        update(Report).where(Report.id == report_id).values(file_path=str(files["document"]), audio_path=str(files["audio"]))
    )
    await db.execute(update(ReportAttachment).where(ReportAttachment.id == ids["photo_id"]).values(path=str(files["photo"])))
    await db.execute(update(DocumentTemplate).where(DocumentTemplate.id == ids["template_id"]).values(file_path=str(files["template"])))
    tenant.logo_path = str(files["logo"])
    db.add_all(
        [
            Job(report_id=report_id, kind="run"),
            ExecutionLog(tenant_id=tenant_id, report_id=report_id, step="extract", status="ok"),
            ReportRevision(report_id=report_id, user_id=admin.id, action="edit"),
            InboundMessage(connection_id=ids["connection_id"], external_id=uuid.uuid4().hex),
            PasswordResetToken(tenant_user_id=admin.id, token_hash=uuid.uuid4().hex, expires_at=datetime.now(UTC) + timedelta(hours=1)),
            AuditEvent(tenant_id=tenant_id, actor_id=admin.id, action="auth.login_succeeded"),
        ]
    )
    await db.commit()
    return {**company, "files": files}


async def _owned_rows(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    """For every table, how many rows hang off the company through any foreign key, directly or
    through one of its users, channels, document types or reports."""
    owned = {
        "tenants": [tenant_id],
        "tenant_users": list(await db.scalars(select(TenantUser.id).where(TenantUser.tenant_id == tenant_id))),
        "reports": list(await db.scalars(select(Report.id).where(Report.tenant_id == tenant_id))),
    }
    for table in ("channel_connections", "document_types"):
        model = Base.metadata.tables[table]
        owned[table] = list(await db.scalars(select(model.c.id).where(model.c.tenant_id == tenant_id)))
    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if owned.get(parent):
                counts[table.name] = counts.get(table.name, 0) + (
                    await db.scalar(select(func.count()).select_from(table).where(fk.parent.in_(owned[parent]))) or 0
                )
    return counts


async def _ask_to_delete(db: AsyncSession, tenant: Tenant, days_ago: int) -> None:
    tenant.is_active = False
    tenant.deletion_requested_at = datetime.now(UTC) - timedelta(days=days_ago)
    await db.commit()


async def test_the_purge_leaves_nothing_of_the_company_and_touches_no_other(
    db: AsyncSession, storage: Path, forgotten_threads: list[str]
) -> None:
    acme, rival = await _full_company(db, "Acme", storage), await _full_company(db, "Rival", storage)
    before, rival_before = await _owned_rows(db, acme["tenant"].id), await _owned_rows(db, rival["tenant"].id)
    # Every table that can hold a company's rows holds some, or the test would prove nothing for it.
    assert all(before.values()), {table: n for table, n in before.items() if not n}
    await _ask_to_delete(db, acme["tenant"], days_ago=31)

    purged = await data_lifecycle.purge_due_tenants(db)

    assert purged == [acme["tenant"].id]
    after = await _owned_rows(db, acme["tenant"].id)
    assert not any(after.values()), {table: n for table, n in after.items() if n}
    assert await _owned_rows(db, rival["tenant"].id) == rival_before
    assert forgotten_threads == [str(acme["ids"]["report_id"])]
    assert not any(path.exists() for path in acme["files"].values())
    assert all(path.exists() for path in rival["files"].values())
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "tenant.purged"))
    assert event is not None and event.tenant_id is None and event.target == str(acme["tenant"].id)


async def test_a_company_in_its_grace_period_or_reactivated_is_not_purged(
    db: AsyncSession, storage: Path, forgotten_threads: list[str]
) -> None:
    waiting, reactivated = await _company(db, "Waiting"), await _company(db, "Back")
    await _ask_to_delete(db, waiting["tenant"], days_ago=29)
    await _ask_to_delete(db, reactivated["tenant"], days_ago=31)
    reactivated["tenant"].is_active = True
    await db.commit()

    assert await data_lifecycle.purge_due_tenants(db) == []
    assert forgotten_threads == []


async def test_a_file_outside_the_storage_folder_is_never_deleted(
    db: AsyncSession, storage: Path, tmp_path_factory: pytest.TempPathFactory, forgotten_threads: list[str]
) -> None:
    acme = await _company(db, "Acme")
    elsewhere = tmp_path_factory.mktemp("elsewhere") / "keep.ogg"
    elsewhere.write_bytes(b"not ours")
    await db.execute(update(Report).where(Report.id == acme["ids"]["report_id"]).values(audio_path=str(elsewhere)))
    await _ask_to_delete(db, acme["tenant"], days_ago=31)

    await data_lifecycle.purge_due_tenants(db)

    assert elsewhere.exists()


async def _delete(client: AsyncClient, user: TenantUser, password: str, name: str) -> Any:
    return await client.request(
        "DELETE", "/company", json={"password": password, "company_name": name}, headers=_auth(user)
    )


async def test_deleting_needs_the_password_and_the_exact_name(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db, "Acme")
    tenant, admin = acme["tenant"], acme["admin"]

    assert (await _delete(client, admin, "wrong", tenant.name)).status_code == 400
    assert (await _delete(client, admin, PASSWORD, "Acme Ltd")).status_code == 400
    await db.refresh(tenant)
    assert tenant.is_active and tenant.deletion_requested_at is None


async def test_deleting_blocks_the_company_at_once(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db, "Acme")
    tenant, admin = acme["tenant"], acme["admin"]

    response = await _delete(client, admin, PASSWORD, f"  {tenant.name} ")

    assert response.status_code == 202
    purge_after = datetime.fromisoformat(response.json()["purge_after"])
    assert abs(purge_after - (datetime.now(UTC) + data_lifecycle.DELETION_GRACE)) < timedelta(minutes=1)
    assert (await client.get("/auth/me", headers=_auth(admin))).status_code == 401
    assert (await client.get("/auth/me", headers=_auth(acme["technician"]))).status_code == 401
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "company.deletion_requested"))
    assert event is not None and event.tenant_id == tenant.id


async def test_wrong_passwords_spend_the_login_attempts(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db, "Acme")

    statuses = [(await _delete(client, acme["admin"], "wrong", acme["tenant"].name)).status_code for _ in range(6)]

    assert statuses == [400] * 5 + [429]


async def test_only_an_admin_can_delete_and_never_on_a_single_company_installation(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    acme = await _company(db, "Acme")
    approver = await db.scalar(select(TenantUser).where(TenantUser.tenant_id == acme["tenant"].id, TenantUser.role == "approver"))
    assert approver is not None
    assert (await _delete(client, approver, PASSWORD, acme["tenant"].name)).status_code == 403

    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    assert (await _delete(client, acme["admin"], PASSWORD, acme["tenant"].name)).status_code == 404


async def test_reactivating_the_company_cancels_its_deletion(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db, "Acme")
    await _ask_to_delete(db, acme["tenant"], days_ago=3)
    support = TenantUser(email="support@reportai.test", hashed_password=hash_password(PASSWORD), full_name="Support", role="super_admin", is_active=True)
    db.add(support)
    await db.commit()

    listed = await client.get(f"/admin/tenants/{acme['tenant'].id}", headers=_auth(support))
    assert listed.json()["deletion_requested_at"] is not None
    response = await client.patch(f"/admin/tenants/{acme['tenant'].id}", json={"is_active": True}, headers=_auth(support))

    assert response.status_code == 200 and response.json()["deletion_requested_at"] is None
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "company.deletion_cancelled"))
    assert event is not None and event.tenant_id == acme["tenant"].id


async def test_voice_notes_expire_and_their_transcript_stays(
    db: AsyncSession, storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acme = await _company(db, "Acme")
    old_id = acme["ids"]["report_id"]
    old_audio, new_audio = _put(storage, f"{old_id}/audio.ogg"), _put(storage, "new/audio.ogg")
    new = Report(
        tenant_id=acme["tenant"].id, status="delivered", requester_channel="telegram", requester_identifier="42",
        audio_path=str(new_audio),
    )
    db.add(new)
    await db.execute(
        update(Report).where(Report.id == old_id).values(
            audio_path=str(old_audio), source_text="what was said", created_at=datetime.now(UTC) - timedelta(days=91)
        )
    )
    await db.commit()

    assert await data_lifecycle.drop_expired_audio(db) == 0  # 0 days: kept for good, as always

    monkeypatch.setattr(settings, "AUDIO_RETENTION_DAYS", 90)
    assert await data_lifecycle.drop_expired_audio(db) == 1
    await db.commit()
    old = await db.scalar(select(Report).where(Report.id == old_id).execution_options(populate_existing=True))
    assert old is not None and old.audio_path is None and old.source_text == "what was said"
    assert not old_audio.exists() and new_audio.exists()


async def test_stale_inbound_files_and_delivery_ids_are_swept(db: AsyncSession, storage: Path) -> None:
    acme = await _company(db, "Acme")
    stale, fresh = _put(storage, "inbound_tmp/stale.ogg"), _put(storage, "inbound_tmp/fresh.ogg")
    three_days_ago = time.time() - 3 * 86400
    os.utime(stale, (three_days_ago, three_days_ago))
    connection_id = acme["ids"]["connection_id"]
    db.add_all(
        [
            InboundMessage(connection_id=connection_id, external_id="old", received_at=datetime.now(UTC) - timedelta(days=31)),
            InboundMessage(connection_id=connection_id, external_id="recent"),
        ]
    )
    await db.commit()

    data_lifecycle.drop_stale_inbound_files()
    await data_lifecycle.prune_inbound_ids(db)
    await db.commit()

    assert not stale.exists() and fresh.exists()
    assert list(await db.scalars(select(InboundMessage.external_id))) == ["recent"]
