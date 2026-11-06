"""One company can never reach another's data, whatever the route.

Two companies get one of everything. Each route that takes an id is called with company A's ids
by people of company B, with a valid body (an invalid one would be refused with 422 before the
scoping check runs, and the test would prove nothing): it must answer 404, never touching A's
rows. The guard test fails as soon as a route with an id exists that nobody classified here.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.channel_connection import ChannelConnection
from app.models.delivery import Delivery
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.report_attachment import ReportAttachment
from app.models.sender_invite import SenderInvite
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

_HASH = hash_password("x")  # bcrypt is slow on purpose: hash once, not per user

# Routes whose ids are not one company's rows: the super admin's (every company is theirs),
# webhooks (authenticated by the channel's own secret, tested with each channel), and the
# starter-template catalog (shared by everyone; installing one creates it in the caller's company).
NOT_TENANT_ROWS = ("/admin/tenants/", "/webhooks/", "/starter-templates/")

DOCX = ("x.docx", b"PK\x03\x04 not really a docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# (method, path) → how to call it: the body or upload that would be valid for the owner.
ID_ROUTES: dict[tuple[str, str], dict[str, Any]] = {
    ("GET", "/document-types/{document_type_id}"): {},
    ("PATCH", "/document-types/{document_type_id}"): {"json": {"name": "Taken over"}},
    ("GET", "/document-types/{document_type_id}/templates"): {},
    ("POST", "/document-types/{document_type_id}/templates"): {"files": {"file": DOCX}},
    ("GET", "/document-types/{document_type_id}/templates/{template_id}/download"): {},
    ("POST", "/document-types/{document_type_id}/template-assistant"): {"files": {"file": DOCX}},
    ("POST", "/document-types/{document_type_id}/template-assistant/{draft_id}/preview"): {"json": {"proposal": {}}},
    ("POST", "/document-types/{document_type_id}/template-assistant/{draft_id}/apply"): {"json": {}},
    ("GET", "/channels/{connection_id}"): {},
    ("PATCH", "/channels/{connection_id}"): {"json": {"display_name": "Taken over"}},
    ("GET", "/channels/{connection_id}/invites"): {},
    ("POST", "/channels/{connection_id}/invites"): {"json": {"label": "Intruder"}},
    ("DELETE", "/channels/{connection_id}/invites/{invite_id}"): {},
    ("GET", "/reports/{report_id}"): {},
    ("POST", "/reports/{report_id}/approve"): {"json": {}},
    ("POST", "/reports/{report_id}/reject"): {"json": {"reason": "x"}},
    ("POST", "/reports/{report_id}/retry"): {},
    ("PATCH", "/reports/{report_id}/fields"): {"json": {"fields": {}}},
    ("POST", "/reports/{report_id}/preview"): {"json": {"fields": {}}},
    ("POST", "/reports/{report_id}/resend"): {"json": {"email": "intruder@evil.test"}},
    ("GET", "/reports/{report_id}/download"): {},
    ("GET", "/reports/{report_id}/audio"): {},
    ("GET", "/reports/{report_id}/photos/{photo_id}"): {},
    ("PATCH", "/team/{member_id}"): {"json": {"is_active": False}},
    ("POST", "/team/{member_id}/invite"): {},
    ("POST", "/team/{member_id}/sign-out"): {},
}


def _id_routes_in_the_app() -> set[tuple[str, str]]:
    routes = set()
    for path, operations in app.openapi()["paths"].items():
        if "{" in path and not path.startswith(NOT_TENANT_ROWS):
            routes |= {(method.upper(), path) for method in operations}
    return routes


def test_every_route_with_an_id_is_in_the_isolation_matrix() -> None:
    unclassified = _id_routes_in_the_app() - ID_ROUTES.keys()
    gone = ID_ROUTES.keys() - _id_routes_in_the_app()
    assert not unclassified, f"Add these routes to ID_ROUTES (or NOT_TENANT_ROWS, with a reason): {unclassified}"
    assert not gone, f"These routes no longer exist; remove them from ID_ROUTES: {gone}"


def _auth(user: TenantUser) -> dict[str, str]:
    token = create_access_token(
        {"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


async def _company(db: AsyncSession, name: str) -> dict[str, Any]:
    tenant = Tenant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()

    def person(role: str) -> TenantUser:
        return TenantUser(
            tenant_id=tenant.id,
            email=f"{role}-{uuid.uuid4().hex[:6]}@{name.lower()}.test",
            hashed_password=_HASH,
            full_name=f"{name} {role}",
            role=role,
            is_active=True,
        )

    admin, member, technician = person("tenant_admin"), person("approver"), person("technician")
    doc_type = DocumentType(tenant_id=tenant.id, name=f"{name} visit", field_schema={})
    connection = ChannelConnection(
        tenant_id=tenant.id,
        channel_type="telegram",
        display_name=f"{name} bot",
        credentials={"bot_token": "t", "secret_token": "s"},
        allowed_senders=["42"],
        is_active=True,
    )
    db.add_all([admin, member, technician, doc_type, connection])
    await db.flush()
    template = DocumentTemplate(tenant_id=tenant.id, document_type_id=doc_type.id, file_path="/nonexistent.docx")
    invite = SenderInvite(
        tenant_id=tenant.id,
        connection_id=connection.id,
        label="Ana",
        code_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    report = Report(
        tenant_id=tenant.id,
        document_type_id=doc_type.id,
        channel_connection_id=connection.id,
        status="awaiting_approval",
        requester_channel="telegram",
        requester_identifier="42",
        requester_user_id=technician.id,
        extracted_fields={"site": f"{name} site"},
    )
    db.add_all([template, invite, report])
    await db.flush()
    photo = ReportAttachment(tenant_id=tenant.id, report_id=report.id, sender_identifier="42", path="/nonexistent.jpg")
    delivery = Delivery(report_id=report.id, kind="email", destination=f"boss@{name.lower()}.test")
    db.add_all([photo, delivery])
    await db.commit()
    return {
        "tenant": tenant,
        "admin": admin,
        "technician": technician,
        "ids": {
            "document_type_id": doc_type.id,
            "template_id": template.id,
            "draft_id": uuid.uuid4(),
            "connection_id": connection.id,
            "invite_id": invite.id,
            "report_id": report.id,
            "photo_id": photo.id,
            "member_id": member.id,
        },
    }


@pytest.fixture
async def companies(db: AsyncSession) -> tuple[dict[str, Any], dict[str, Any]]:
    return await _company(db, "Acme"), await _company(db, "Rival")


async def _snapshot(db: AsyncSession, tenant: Tenant) -> str:
    """Everything of the company's that a route could change, to compare before and after."""
    rows: list[Any] = []
    fresh = {"populate_existing": True}  # read the database, not the session's copies
    for model in (DocumentType, DocumentTemplate, ChannelConnection, SenderInvite, Report, TenantUser):
        query = select(model).where(model.tenant_id == tenant.id).order_by(model.id).execution_options(**fresh)
        for row in (await db.scalars(query)).all():
            rows.append({c.name: getattr(row, c.key) for c in model.__mapper__.columns if c.name != "updated_at"})
    report_ids = select(Report.id).where(Report.tenant_id == tenant.id)
    deliveries = select(Delivery).where(Delivery.report_id.in_(report_ids)).execution_options(**fresh)
    for delivery in (await db.scalars(deliveries)).all():
        rows.append({c.name: getattr(delivery, c.key) for c in Delivery.__mapper__.columns if c.name != "updated_at"})
    return json.dumps(rows, default=str, sort_keys=True)


@pytest.mark.parametrize("actor", ["admin", "technician"])
@pytest.mark.parametrize(("method", "path"), sorted(ID_ROUTES))
async def test_another_company_gets_404_and_changes_nothing(
    client: AsyncClient,
    db: AsyncSession,
    companies: tuple[dict[str, Any], dict[str, Any]],
    actor: str,
    method: str,
    path: str,
) -> None:
    acme, rival = companies
    headers, url = _auth(rival[actor]), path.format(**acme["ids"])
    before = await _snapshot(db, acme["tenant"])

    response = await client.request(method, url, headers=headers, **ID_ROUTES[(method, path)])

    # A technician is refused panel routes outright (403); anything that gets past the role check
    # must not find the other company's row. Both are fine; what may never happen is a 2xx.
    allowed = {404} if actor == "admin" else {403, 404}
    assert response.status_code in allowed, response.text
    assert await _snapshot(db, acme["tenant"]) == before


LISTS = ["/reports", "/reports/export.csv", "/channels", "/team", "/document-types", "/dashboard", "/usage/summary", "/audit"]


@pytest.mark.parametrize("path", LISTS)
async def test_lists_and_totals_never_show_another_company(
    client: AsyncClient, companies: tuple[dict[str, Any], dict[str, Any]], path: str
) -> None:
    acme, rival = companies

    response = await client.get(path, headers=_auth(rival["admin"]))

    assert response.status_code == 200
    for value in [*acme["ids"].values(), "Acme"]:
        assert str(value) not in response.text, f"{path} leaked {value}"
