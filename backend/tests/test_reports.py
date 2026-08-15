import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.agent import invoke


async def _create_tenant_admin(db: AsyncSession, *, name: str = "Acme", slug: str = "acme") -> TenantUser:
    tenant = Tenant(name=name, slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email=f"admin@{slug}.test",
        hashed_password=hash_password("correct-password"),
        full_name="Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": "correct-password"})
    return str(response.json()["access_token"])


def _make_report(tenant_id, *, status: str, file_path: str | None = None) -> Report:
    return Report(
        tenant_id=tenant_id,
        status=status,
        requester_channel="telegram",
        requester_identifier="12345",
        file_path=file_path,
    )


async def test_list_reports_paginated_and_filtered(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    db.add_all(
        [
            _make_report(user.tenant_id, status="delivered"),
            _make_report(user.tenant_id, status="delivered"),
            _make_report(user.tenant_id, status="failed"),
        ]
    )
    await db.commit()

    all_response = await client.get("/reports?skip=0&limit=10", headers=headers)
    assert all_response.json()["total"] == 3

    filtered_response = await client.get("/reports?status=failed", headers=headers)
    body = filtered_response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "failed"


async def test_reports_are_tenant_isolated(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    db.add(_make_report(owner.tenant_id, status="delivered"))
    db.add(_make_report(other.tenant_id, status="delivered"))
    await db.commit()

    other_token = await _login(client, other.email)
    response = await client.get("/reports", headers={"Authorization": f"Bearer {other_token}"})

    assert response.json()["total"] == 1


async def test_get_report_cross_tenant_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    report = _make_report(owner.tenant_id, status="delivered")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    other_token = await _login(client, other.email)
    response = await client.get(
        f"/reports/{report.id}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404


async def test_approve_resumes_awaiting_report(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    report = _make_report(user.tenant_id, status="awaiting_approval")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    resume_mock = AsyncMock()
    monkeypatch.setattr(invoke, "_resume_graph", resume_mock)

    response = await client.post(
        f"/reports/{report.id}/approve", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"  # claimed for the in-flight resume
    resume_mock.assert_awaited_once_with(str(report.id), "CONFIRM")


async def test_approve_conflict_when_not_awaiting(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    report = _make_report(user.tenant_id, status="delivered")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    response = await client.post(
        f"/reports/{report.id}/approve", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 409


async def test_approve_cross_tenant_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    report = _make_report(owner.tenant_id, status="awaiting_approval")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    other_token = await _login(client, other.email)
    response = await client.post(
        f"/reports/{report.id}/approve", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404


async def test_reject_marks_paused_report_failed(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    report = _make_report(user.tenant_id, status="awaiting_approval")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    response = await client.post(
        f"/reports/{report.id}/reject", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_detail"] == "Rejected by admin"
    assert body["completed_at"] is not None


async def test_reject_conflict_when_not_paused(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    report = _make_report(user.tenant_id, status="delivered")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    response = await client.post(
        f"/reports/{report.id}/reject", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 409


async def test_download_report_returns_file_for_own_tenant(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake pdf content")
        file_path = f.name

    report = _make_report(user.tenant_id, status="delivered", file_path=file_path)
    db.add(report)
    await db.commit()
    await db.refresh(report)

    response = await client.get(
        f"/reports/{report.id}/download", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fake pdf content"
    Path(file_path).unlink(missing_ok=True)


async def test_download_report_cross_tenant_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    report = _make_report(owner.tenant_id, status="delivered", file_path="/tmp/whatever.pdf")
    db.add(report)
    await db.commit()
    await db.refresh(report)

    other_token = await _login(client, other.email)
    response = await client.get(
        f"/reports/{report.id}/download", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404


async def test_download_report_with_no_file_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    report = _make_report(user.tenant_id, status="pending", file_path=None)
    db.add(report)
    await db.commit()
    await db.refresh(report)

    response = await client.get(
        f"/reports/{report.id}/download", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
