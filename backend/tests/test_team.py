"""A company's people: an admin runs everything, an approver reviews and sends reports, a viewer
only reads them. People are invited with a link to choose their own password, and a change of
role or a deactivation ends their open sessions."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.notifications import invites


async def _company(db: AsyncSession, language: str = "es") -> Tenant:
    tenant = Tenant(name="Reformas García", slug=f"garcia-{uuid.uuid4().hex[:6]}", is_active=True, language=language)
    db.add(tenant)
    await db.flush()
    return tenant


async def _person(db: AsyncSession, tenant: Tenant, role: str) -> TenantUser:
    user = TenantUser(
        tenant_id=tenant.id, email=f"{role}-{uuid.uuid4().hex[:6]}@garcia.test",
        hashed_password=hash_password("correct-password"), full_name=role.title(), role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser, password: str = "correct-password") -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    send = AsyncMock()
    monkeypatch.setattr(invites, "send_plain_email", send)
    return send


async def test_each_role_reaches_what_it_is_for(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _company(db)
    report = Report(tenant_id=tenant.id, status="awaiting_details", requester_channel="telegram", requester_identifier="42")
    db.add(report)
    await db.commit()
    viewer = await _headers(client, await _person(db, tenant, "viewer"))
    approver = await _headers(client, await _person(db, tenant, "approver"))
    admin = await _headers(client, await _person(db, tenant, "tenant_admin"))

    for headers in (viewer, approver, admin):
        assert (await client.get("/reports", headers=headers)).status_code == 200
        assert (await client.get(f"/reports/{report.id}", headers=headers)).status_code == 200
        assert (await client.get("/document-types", headers=headers)).status_code == 200

    assert (await client.post(f"/reports/{report.id}/reject", json={}, headers=viewer)).status_code == 403
    assert (await client.post(f"/reports/{report.id}/reject", json={}, headers=approver)).status_code == 200

    new_type = {"name": "Visita", "field_schema": {}}
    assert (await client.post("/document-types", json=new_type, headers=approver)).status_code == 403
    assert (await client.get("/team", headers=approver)).status_code == 403
    assert (await client.get("/channels", headers=viewer)).status_code == 403
    assert (await client.get("/team", headers=admin)).status_code == 200


async def test_an_invited_person_chooses_their_own_password(
    client: AsyncClient, db: AsyncSession, mail: AsyncMock
) -> None:
    tenant = await _company(db)
    admin = await _headers(client, await _person(db, tenant, "tenant_admin"))

    invited = await client.post(
        "/team", json={"email": "ana@garcia.test", "full_name": "Ana Ruiz", "role": "approver"}, headers=admin
    )

    assert invited.status_code == 201
    assert invited.json()["invite_email_sent"] is True and invited.json()["invite_link"] is None
    email = mail.await_args.kwargs
    assert email["to"] == ["ana@garcia.test"] and "Reformas García" in email["subject"]
    assert "Hola, Ana Ruiz" in email["body"] and "7 días" in email["body"]  # in the company's language
    token = email["body"].split("token=")[1].split()[0]

    assert (await client.post("/auth/reset-password", json={"token": token, "new_password": "ana-password-1"})).status_code == 200
    login = await client.post("/auth/login", json={"email": "ana@garcia.test", "password": "ana-password-1"})
    assert login.status_code == 200

    again = await client.post("/team", json={"email": "ana@garcia.test", "full_name": "Ana", "role": "viewer"}, headers=admin)
    assert again.status_code == 409


async def test_without_a_mail_server_the_admin_gets_the_link_to_pass_on(
    client: AsyncClient, db: AsyncSession, mail: AsyncMock
) -> None:
    mail.side_effect = RuntimeError("Email isn't configured")
    tenant = await _company(db)
    admin = await _headers(client, await _person(db, tenant, "tenant_admin"))

    invited = await client.post("/team", json={"email": "luis@garcia.test", "full_name": "Luis", "role": "viewer"}, headers=admin)

    assert invited.json()["invite_email_sent"] is False
    assert "/reset-password?token=" in invited.json()["invite_link"]


async def test_a_change_of_role_or_a_deactivation_ends_their_sessions(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _company(db)
    admin = await _headers(client, await _person(db, tenant, "tenant_admin"))
    approver_user = await _person(db, tenant, "approver")
    approver = await _headers(client, approver_user)

    demoted = await client.patch(f"/team/{approver_user.id}", json={"role": "viewer"}, headers=admin)

    assert demoted.json()["role"] == "viewer"
    assert (await client.get("/auth/me", headers=approver)).status_code == 401
    viewer = await _headers(client, approver_user)
    assert (await client.get("/auth/me", headers=viewer)).json()["role"] == "viewer"

    await client.patch(f"/team/{approver_user.id}", json={"is_active": False}, headers=admin)
    assert (await client.get("/auth/me", headers=viewer)).status_code == 401
    assert (await client.post("/auth/login", json={"email": approver_user.email, "password": "correct-password"})).status_code == 401


async def test_an_admin_cannot_lock_themselves_out(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _company(db)
    admin_user = await _person(db, tenant, "tenant_admin")
    admin = await _headers(client, admin_user)

    for change in ({"role": "viewer"}, {"is_active": False}):
        response = await client.patch(f"/team/{admin_user.id}", json=change, headers=admin)
        assert response.status_code == 400

    renamed = await client.patch(f"/team/{admin_user.id}", json={"full_name": "Lucía García"}, headers=admin)
    assert renamed.json()["full_name"] == "Lucía García"


async def test_another_companys_people_are_out_of_reach(client: AsyncClient, db: AsyncSession) -> None:
    ours, theirs = await _company(db), await _company(db)
    admin = await _headers(client, await _person(db, ours, "tenant_admin"))
    stranger = await _person(db, theirs, "approver")

    assert (await client.patch(f"/team/{stranger.id}", json={"role": "viewer"}, headers=admin)).status_code == 404
    assert stranger.email not in (await client.get("/team", headers=admin)).text


async def test_changing_your_own_password_keeps_you_signed_in_here_only(client: AsyncClient, db: AsyncSession) -> None:
    tenant = await _company(db)
    user = await _person(db, tenant, "viewer")
    other_device = await _headers(client, user)
    here = await _headers(client, user)

    wrong = await client.post("/auth/change-password", json={"current_password": "nope", "new_password": "new-password-1"}, headers=here)
    assert wrong.status_code == 400

    changed = await client.post(
        "/auth/change-password", json={"current_password": "correct-password", "new_password": "new-password-1"}, headers=here
    )
    assert changed.status_code == 200
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert (await client.get("/auth/me", headers=fresh)).status_code == 200
    assert (await client.get("/auth/me", headers=other_device)).status_code == 401

    renamed = await client.patch("/auth/me", json={"full_name": "Ana Ruiz"}, headers=fresh)
    assert renamed.json()["full_name"] == "Ana Ruiz"
