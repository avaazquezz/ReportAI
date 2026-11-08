"""The app as a channel: a technician records a report in the browser, retries safely, and reviews,
corrects and confirms their own draft on screen. Nobody else's, and only within the plan."""

import io
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.channel_connection import ChannelConnection
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.job import Job
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import instance_settings

_HASH = hash_password("x")
_WEBM = ("note.webm", b"\x1aE\xdf\xa3 not really webm", "audio/webm;codecs=opus")


@pytest.fixture(autouse=True)
def _ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def configured(session: object = None) -> dict[str, str]:
        return {"extraction_api_key": "k", "transcription_api_key": "k"}

    monkeypatch.setattr(instance_settings, "load", configured)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))


def _png() -> tuple[str, bytes, str]:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "orange").save(out, "PNG")
    return ("site.png", out.getvalue(), "image/png")


def _auth(user: TenantUser) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": 0})
    return {"Authorization": f"Bearer {token}"}


async def _company(db: AsyncSession, name: str = "Acme") -> dict[str, Any]:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    people = {
        role: TenantUser(
            tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:6]}@acme.test", hashed_password=_HASH,
            full_name=f"{name} {role}", role=role, is_active=True,
        )
        for role in ("technician", "approver", "viewer", "tenant_admin")
    }
    colleague = TenantUser(
        tenant_id=tenant.id, email=f"luis-{uuid.uuid4().hex[:6]}@acme.test", hashed_password=_HASH,
        full_name="Luis", role="technician", is_active=True,
    )
    doc_type = DocumentType(tenant_id=tenant.id, name="Visita de obra", field_schema={}, is_active=True)
    db.add_all([*people.values(), colleague, doc_type])
    await db.commit()
    return {"tenant": tenant, "doc_type": doc_type, "colleague": colleague, **people}


async def _capture(
    client: AsyncClient, user: TenantUser, doc_type: DocumentType, *, key: uuid.UUID | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None, text: str | None = None,
) -> Response:
    data = {"document_type_id": str(doc_type.id)} | ({"text": text} if text else {})
    return await client.post(
        "/capture", data=data, files=files if files is not None else [("audio", _WEBM)],
        headers=_auth(user) | {"Idempotency-Key": str(key or uuid.uuid4())},
    )


async def _count(db: AsyncSession, model: type) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def test_a_technician_records_a_report_with_photos(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    key = uuid.uuid4()

    response = await _capture(client, acme["technician"], acme["doc_type"], key=key, files=[("audio", _WEBM), ("photos", _png())])

    assert response.status_code == 202, response.text
    assert response.json() == {"id": str(key), "status": "pending"}
    report = await db.get(Report, key)
    assert report is not None and report.requester_channel == "web" and report.requester_user_id == acme["technician"].id
    job = await db.scalar(select(Job).where(Job.report_id == key))
    assert job is not None and job.payload["document_type_id"] == str(acme["doc_type"].id)
    assert job.payload["media_reference"].endswith(".webm") and Path(job.payload["media_reference"]).exists()
    photo = await db.scalar(select(ReportAttachment).where(ReportAttachment.report_id == key))
    assert photo is not None and Path(photo.path).exists()
    # The app's connection exists, one per company, and stays out of the Channels page.
    connections = list(await db.scalars(select(ChannelConnection).where(ChannelConnection.tenant_id == acme["tenant"].id)))
    assert [c.channel_type for c in connections] == ["web"]
    listed = await client.get("/channels", headers=_auth(acme["tenant_admin"]))
    assert listed.json()["total"] == 0


async def test_a_retry_returns_the_same_report_and_a_borrowed_key_is_refused(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    key = uuid.uuid4()

    first = await _capture(client, acme["technician"], acme["doc_type"], key=key)
    again = await _capture(client, acme["technician"], acme["doc_type"], key=key)
    borrowed = await _capture(client, acme["colleague"], acme["doc_type"], key=key)

    assert first.json() == again.json() and await _count(db, Report) == 1
    assert borrowed.status_code == 409


async def test_a_technician_keeps_several_drafts_open(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)

    answers = [await _capture(client, acme["technician"], acme["doc_type"], text=f"Visita {n}") for n in range(2)]

    assert [a.status_code for a in answers] == [202, 202] and await _count(db, Report) == 2


async def test_a_capture_must_be_allowed_complete_and_well_formed(client: AsyncClient, db: AsyncSession) -> None:
    acme, other = await _company(db), await _company(db, "Other")
    switched_off = DocumentType(tenant_id=acme["tenant"].id, name="Old", field_schema={}, is_active=False)
    db.add(switched_off)
    await db.commit()
    technician = acme["technician"]

    assert (await _capture(client, acme["viewer"], acme["doc_type"])).status_code == 403
    assert (await _capture(client, technician, other["doc_type"])).status_code == 404
    assert (await _capture(client, technician, switched_off)).status_code == 400
    assert (await _capture(client, technician, acme["doc_type"], files=[])).status_code == 400  # nothing said
    assert (await _capture(client, technician, acme["doc_type"], files=[("audio", ("a.xyz", b"x", "audio/x-foo"))])).status_code == 400
    not_a_picture = [("audio", _WEBM), ("photos", ("p.jpg", b"not an image", "image/jpeg"))]
    assert (await _capture(client, technician, acme["doc_type"], files=not_a_picture)).status_code == 400
    assert await _count(db, Report) == 0


async def test_a_capture_the_plan_does_not_allow_is_refused_in_the_company_language(
    client: AsyncClient, db: AsyncSession
) -> None:
    acme = await _company(db)
    acme["tenant"].plan_status = "canceled"
    await db.commit()

    response = await _capture(client, acme["technician"], acme["doc_type"])

    assert response.status_code == 402 and "plan" in response.json()["detail"]


async def _draft(db: AsyncSession, acme: dict[str, Any], *, channel: str = "web", status: str = "awaiting_approval") -> Report:
    technician = acme["technician"]
    report = Report(
        tenant_id=acme["tenant"].id, document_type_id=acme["doc_type"].id, status=status, requester_channel=channel,
        requester_identifier=str(technician.id), requester_user_id=technician.id, extracted_fields={},
    )
    db.add(report)
    await db.commit()
    return report


async def test_the_technician_corrects_and_confirms_their_own_draft(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    corrected, confirmed = await _draft(db, acme), await _draft(db, acme)
    technician = acme["technician"]

    reply = await client.post(f"/reports/{corrected.id}/reply", data={"text": "La fecha es mañana"}, headers=_auth(technician))
    approve = await client.post(f"/reports/{confirmed.id}/approve", json={}, headers=_auth(technician))

    assert reply.status_code == 202 and approve.status_code == 202, (reply.text, approve.text)
    jobs = {job.report_id: job.payload for job in await db.scalars(select(Job))}
    assert jobs[corrected.id] == {"text": "La fecha es mañana", "media_reference": None}
    assert jobs[confirmed.id] == {"action": "confirm"}


async def test_replies_are_only_for_the_owner_s_waiting_app_drafts(client: AsyncClient, db: AsyncSession) -> None:
    acme = await _company(db)
    draft, chat, done = await _draft(db, acme), await _draft(db, acme, channel="telegram"), await _draft(db, acme, status="delivered")

    def reply(report: Report, user: TenantUser) -> Any:
        return client.post(f"/reports/{report.id}/reply", data={"text": "x"}, headers=_auth(user))

    assert (await reply(draft, acme["colleague"])).status_code == 404  # a colleague's: as if it didn't exist
    assert (await reply(draft, acme["viewer"])).status_code == 403
    assert (await reply(chat, acme["technician"])).status_code == 409  # a chat report is answered in the chat
    assert (await reply(done, acme["technician"])).status_code == 409
    assert await _count(db, Job) == 0


async def test_the_app_offers_the_active_types_that_can_be_rendered(client: AsyncClient, db: AsyncSession) -> None:
    acme, other = await _company(db), await _company(db, "Other")
    untemplated = DocumentType(tenant_id=acme["tenant"].id, name="Sin plantilla", field_schema={}, is_active=True)
    old = DocumentType(tenant_id=acme["tenant"].id, name="Vieja", field_schema={}, is_active=False)
    db.add_all([untemplated, old])
    await db.flush()
    for doc_type in (acme["doc_type"], old, other["doc_type"]):
        db.add(DocumentTemplate(tenant_id=doc_type.tenant_id, document_type_id=doc_type.id, file_path="x.docx", version=1, is_active=True))
    await db.commit()

    offered = await client.get("/capture/document-types", headers=_auth(acme["technician"]))

    assert offered.status_code == 200
    assert offered.json() == [{"id": str(acme["doc_type"].id), "name": "Visita de obra", "description": None}]
    assert (await client.get("/capture/document-types", headers=_auth(acme["viewer"]))).status_code == 403
