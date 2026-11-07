"""A technician captures reports and reads their own — nothing else of the panel, and none of a
colleague's or another company's reports."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

_HASH = hash_password("x")  # bcrypt is slow on purpose: hash once, not per user


async def _tenant(db: AsyncSession) -> Tenant:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    return tenant


async def _user(db: AsyncSession, tenant: Tenant, role: str, name: str = "Person") -> TenantUser:
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"{role}-{uuid.uuid4().hex[:6]}@acme.test",
        hashed_password=_HASH,
        full_name=name,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _report(db: AsyncSession, tenant: Tenant, owner: TenantUser | None) -> Report:
    report = Report(
        tenant_id=tenant.id,
        status="delivered",
        requester_channel="web" if owner else "telegram",
        requester_identifier=str(owner.id) if owner else "42",
        requester_user_id=owner.id if owner else None,
    )
    db.add(report)
    await db.flush()
    return report


def _auth(user: TenantUser) -> dict[str, str]:
    token = create_access_token(
        {"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id), "ver": user.token_version}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world(db: AsyncSession) -> dict[str, object]:
    acme, other = await _tenant(db), await _tenant(db)
    ana = await _user(db, acme, "technician", "Ana Técnica")
    luis = await _user(db, acme, "technician", "Luis")
    admin = await _user(db, acme, "tenant_admin")
    stranger = await _user(db, other, "technician")
    world = {
        "ana": ana,
        "admin": admin,
        "ana_report": await _report(db, acme, ana),
        "luis_report": await _report(db, acme, luis),
        "chat_report": await _report(db, acme, None),
        "other_report": await _report(db, other, stranger),
    }
    await db.commit()
    return world


# Every panel route a technician must NOT reach. A new route opened to technicians on purpose
# goes in the allowed list below, with its ownership check tested.
PANEL_ONLY = [
    ("GET", "/dashboard"),
    ("GET", "/reports/export.csv"),
    ("GET", "/document-types"),
    ("GET", "/channels"),
    ("GET", "/team"),
    ("GET", "/usage/summary"),
    ("GET", "/company/plan"),
    ("PATCH", "/company"),
]


@pytest.mark.parametrize(("method", "path"), PANEL_ONLY)
async def test_the_panel_is_closed_to_a_technician(
    client: AsyncClient, world: dict[str, object], method: str, path: str
) -> None:
    response = await client.request(method, path, headers=_auth(world["ana"]), json={})  # type: ignore[arg-type]
    assert response.status_code == 403


async def test_a_technician_can_read_their_account_and_the_company_branding(
    client: AsyncClient, world: dict[str, object]
) -> None:
    headers = _auth(world["ana"])  # type: ignore[arg-type]
    assert (await client.get("/auth/me", headers=headers)).status_code == 200
    assert (await client.get("/company", headers=headers)).status_code == 200


async def test_a_technician_lists_only_their_own_reports(client: AsyncClient, world: dict[str, object]) -> None:
    response = await client.get("/reports", headers=_auth(world["ana"]))  # type: ignore[arg-type]

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(world["ana_report"].id)]  # type: ignore[attr-defined]
    assert items[0]["requester_name"] == "Ana Técnica"
    assert response.json()["total"] == 1


@pytest.mark.parametrize("suffix", ["", "/download", "/audio"])
async def test_a_technician_reads_their_report_and_no_one_else_s(
    client: AsyncClient, world: dict[str, object], suffix: str
) -> None:
    headers = _auth(world["ana"])  # type: ignore[arg-type]
    for key in ("luis_report", "chat_report", "other_report"):
        response = await client.get(f"/reports/{world[key].id}{suffix}", headers=headers)  # type: ignore[attr-defined]
        assert response.status_code == 404, key
    own = await client.get(f"/reports/{world['ana_report'].id}", headers=headers)  # type: ignore[attr-defined]
    assert own.status_code == 200


async def test_a_technician_cannot_reject_their_own_report(client: AsyncClient, world: dict[str, object]) -> None:
    # They confirm and correct their drafts from the app (test_capture.py); rejecting is review, the approvers'.
    response = await client.post(
        f"/reports/{world['ana_report'].id}/reject",  # type: ignore[attr-defined]
        json={"reason": "x"},
        headers=_auth(world["ana"]),  # type: ignore[arg-type]
    )
    assert response.status_code == 403


async def test_the_panel_still_sees_every_report_of_the_company(client: AsyncClient, world: dict[str, object]) -> None:
    response = await client.get("/reports", headers=_auth(world["admin"]))  # type: ignore[arg-type]
    assert response.json()["total"] == 3


async def test_a_departed_technician_s_reports_stay(db: AsyncSession, world: dict[str, object]) -> None:
    ana: TenantUser = world["ana"]  # type: ignore[assignment]
    await db.execute(delete(TenantUser).where(TenantUser.id == ana.id))
    await db.commit()

    report: Report = world["ana_report"]  # type: ignore[assignment]
    await db.refresh(report)
    assert report.requester_user_id is None
