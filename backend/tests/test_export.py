"""A company's admin downloads everything ReportAI holds for the company as one zip: its
settings, team, channels, document types and templates, reports with their files, and audit
log — never a secret, never another company's row, at most once an hour."""

import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.audit_event import AuditEvent
from app.models.channel_connection import ChannelConnection
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.report_revision import ReportRevision
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

_HASH = hash_password("x")  # bcrypt is slow on purpose: hash once, not per user
BOT_TOKEN = "123456789:AAE-fake-bot-token-for-the-export"
PDF, AUDIO, PHOTO, LOGO = b"%PDF-1.7 rendered", b"OggS voice note", b"\xff\xd8\xff photo", b"\x89PNG logo"


@dataclass
class Company:
    tenant: Tenant
    admin: TenantUser
    report: Report
    template: DocumentTemplate
    files: Path


async def _person(db: AsyncSession, tenant: Tenant, role: str, email: str | None = None) -> TenantUser:
    user = TenantUser(
        tenant_id=tenant.id, email=email or f"{role}-{uuid.uuid4().hex[:6]}@garcia.test", hashed_password=_HASH,
        full_name="Lucía", role=role, is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _company(db: AsyncSession, folder: Path, *, name: str = "Reformas García") -> Company:
    """One of everything, with its files on disk under `folder`."""
    folder.mkdir()
    (folder / "logo.png").write_bytes(LOGO)
    tenant = Tenant(
        name=name, slug=f"garcia-{uuid.uuid4().hex[:6]}", is_active=True, logo_path=str(folder / "logo.png"),
        reply_to_email="oficina@garcia.test",
    )
    db.add(tenant)
    await db.flush()
    admin = await _person(db, tenant, "tenant_admin")
    db.add(ChannelConnection(
        tenant_id=tenant.id, channel_type="telegram", display_name="Bot obra", credentials={"bot_token": BOT_TOKEN},
        allowed_senders=["42"],
    ))
    document_type = DocumentType(
        tenant_id=tenant.id, name="Visita", field_schema={"cliente": {"type": "string"}}, notification_emails=["jefe@garcia.test"],
    )
    db.add(document_type)
    await db.flush()
    word = Document()
    word.add_paragraph("Cliente: {{ cliente }}")
    word.save(folder / "template.docx")
    template = DocumentTemplate(
        tenant_id=tenant.id, document_type_id=document_type.id, file_path=str(folder / "template.docx"),
        original_filename="Visita.docx", version=1, is_active=True,
    )
    (folder / "rendered.pdf").write_bytes(PDF)
    (folder / "audio.ogg").write_bytes(AUDIO)
    (folder / "photo.jpg").write_bytes(PHOTO)
    report = Report(
        tenant_id=tenant.id, document_type_id=document_type.id, status="delivered", requester_channel="telegram",
        requester_identifier="42", source_text=f"Visita para {name}", extracted_fields={"cliente": name},
        file_path=str(folder / "rendered.pdf"), audio_path=str(folder / "audio.ogg"),
    )
    db.add_all([template, report])
    await db.flush()
    db.add_all([
        ReportAttachment(tenant_id=tenant.id, report_id=report.id, sender_identifier="42", path=str(folder / "photo.jpg")),
        ReportRevision(report_id=report.id, user_id=admin.id, action="edit", changes={"cliente": {"from": "x", "to": name}}),
    ])
    await db.commit()
    return Company(tenant=tenant, admin=admin, report=report, template=template, files=folder)


def _headers(user: TenantUser) -> dict[str, str]:
    claims = {"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": user.token_version}
    return {"Authorization": f"Bearer {create_access_token(claims)}"}


def _unzip(response: Response) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _json(files: dict[str, bytes], name: str) -> Any:
    return json.loads(files[name])


@pytest.mark.parametrize("single_tenant", [False, True])
async def test_the_admin_downloads_everything_the_company_holds(
    client: AsyncClient, db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, single_tenant: bool
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", single_tenant)
    company = await _company(db, tmp_path / "garcia")
    db.add(AuditEvent(tenant_id=company.tenant.id, actor_id=company.admin.id, action="auth.login_succeeded"))
    await db.commit()

    response = await client.get("/company/export", headers=_headers(company.admin))

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    disposition = rf'attachment; filename="reportai-export-{company.tenant.slug}-\d{{4}}-\d{{2}}-\d{{2}}\.zip"'
    assert re.fullmatch(disposition, response.headers["content-disposition"])
    files = _unzip(response)
    report_id, template_id = company.report.id, company.template.id

    manifest = _json(files, "manifest.json")
    assert manifest["format_version"] == 1 and manifest["company"] == company.tenant.slug
    assert manifest["counts"] == {
        "team": 1, "channels": 1, "document_types": 1, "templates": 1, "reports": 1, "revisions": 1,
        "audit_events": 1, "files": 5,
    }
    assert manifest["missing_files"] == []
    assert _json(files, "company.json") == {
        "name": "Reformas García", "slug": company.tenant.slug, "language": "es", "timezone": "Europe/Madrid",
        "brand_color": None, "reply_to_email": "oficina@garcia.test", "plan": "unlimited", "plan_status": "active",
        "created_at": company.tenant.created_at.isoformat(), "logo": "branding/logo.png",
    }
    [member] = _json(files, "team.json")
    assert set(member) == {"full_name", "email", "role", "is_active", "created_at", "email_verified_at"}
    assert member["email"] == company.admin.email
    [channel] = _json(files, "channels.json")
    assert channel["display_name"] == "Bot obra" and channel["allowed_senders"] == ["42"] and "credentials" not in channel
    [document_type] = _json(files, "document_types.json")
    assert document_type["field_schema"] == {"cliente": {"type": "string"}}
    assert document_type["templates"] == [{
        "original_filename": "Visita.docx", "version": 1, "is_active": True,
        "created_at": company.template.created_at.isoformat(), "file": f"templates/{template_id}.docx",
    }]
    [report] = _json(files, "reports.json")
    assert report["id"] == str(report_id) and report["document_type"] == "Visita"
    assert report["extracted_fields"] == {"cliente": "Reformas García"} and report["source_text"] == "Visita para Reformas García"
    assert report["revisions"][0]["author"] == company.admin.email and report["revisions"][0]["action"] == "edit"
    [photo] = await db.scalars(select(ReportAttachment.id))
    assert report["files"] == [
        f"reports/{report_id}/document.pdf", f"reports/{report_id}/audio.ogg", f"reports/{report_id}/photos/{photo}.jpg",
    ]
    assert files[f"templates/{template_id}.docx"] == (company.files / "template.docx").read_bytes()
    assert Document(io.BytesIO(files[f"templates/{template_id}.docx"])).paragraphs[0].text == "Cliente: {{ cliente }}"
    assert files[f"reports/{report_id}/document.pdf"] == PDF
    assert files[f"reports/{report_id}/audio.ogg"] == AUDIO
    assert files[f"reports/{report_id}/photos/{photo}.jpg"] == PHOTO
    assert files["branding/logo.png"] == LOGO

    [event] = await db.scalars(select(AuditEvent).where(AuditEvent.action == "company.exported"))
    assert (event.actor_id, event.tenant_id, event.target) == (company.admin.id, company.tenant.id, str(company.tenant.id))
    # The log as it stood: the export's own event is recorded once the zip is built.
    assert [e["action"] for e in _json(files, "audit_events.json")] == ["auth.login_succeeded"]


async def test_the_export_holds_no_secret_and_nothing_of_another_company(
    client: AsyncClient, db: AsyncSession, tmp_path: Path
) -> None:
    company = await _company(db, tmp_path / "garcia")
    other = await _company(db, tmp_path / "other", name="OTHER-COMPANY-SECRET")
    await _person(db, other.tenant, "approver", email="intruder@other.test")
    await db.commit()

    response = await client.get("/company/export", headers=_headers(company.admin))

    assert response.status_code == 200
    everything = b"".join(_unzip(response).values()).decode("utf-8", errors="replace")
    for secret in (BOT_TOKEN, _HASH, "hashed_password", "token_version", "credentials"):
        assert secret not in everything, secret
    for foreign in ("intruder@other.test", other.admin.email, "OTHER-COMPANY-SECRET", str(other.report.id), other.tenant.slug):
        assert foreign not in everything, foreign


async def test_a_second_export_within_the_hour_is_refused(client: AsyncClient, db: AsyncSession, tmp_path: Path) -> None:
    company = await _company(db, tmp_path / "garcia")
    other = await _company(db, tmp_path / "other")

    first = await client.get("/company/export", headers=_headers(company.admin))
    again = await client.get("/company/export", headers=_headers(company.admin))
    another_company = await client.get("/company/export", headers=_headers(other.admin))

    assert (first.status_code, again.status_code, another_company.status_code) == (200, 429, 200)
    assert 0 < int(again.headers["retry-after"]) <= 3600


async def test_an_export_that_fails_can_be_retried_at_once(
    client: AsyncClient, db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    company = await _company(db, tmp_path / "garcia")

    async def disk_full(*_: object) -> Path:
        raise OSError("No space left on device")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.export.build", disk_full)
        with pytest.raises(OSError):
            await client.get("/company/export", headers=_headers(company.admin))

    assert (await client.get("/company/export", headers=_headers(company.admin))).status_code == 200


@pytest.mark.parametrize("role", ["approver", "viewer", "technician"])
async def test_only_the_admin_exports(client: AsyncClient, db: AsyncSession, tmp_path: Path, role: str) -> None:
    company = await _company(db, tmp_path / "garcia")
    person = await _person(db, company.tenant, role)
    await db.commit()

    refused = await client.get("/company/export", headers=_headers(person))

    assert refused.status_code == 403
    assert (await client.get("/company/export", headers=_headers(company.admin))).status_code == 200  # no hour spent


async def test_a_file_gone_from_disk_is_listed_and_the_export_still_succeeds(
    client: AsyncClient, db: AsyncSession, tmp_path: Path
) -> None:
    company = await _company(db, tmp_path / "garcia")
    (company.files / "audio.ogg").unlink()

    response = await client.get("/company/export", headers=_headers(company.admin))

    assert response.status_code == 200
    files = _unzip(response)
    assert _json(files, "manifest.json")["missing_files"] == [str(company.files / "audio.ogg")]
    [report] = _json(files, "reports.json")
    assert f"reports/{company.report.id}/audio.ogg" not in report["files"] and len(report["files"]) == 2
    assert f"reports/{company.report.id}/audio.ogg" not in files
