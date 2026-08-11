from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


async def _create_super_admin(db: AsyncSession) -> TenantUser:
    user = TenantUser(
        tenant_id=None,
        email="root@reportai.dev",
        hashed_password=hash_password("super-secret-password"),
        full_name="Root Admin",
        role="super_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_tenant_admin(db: AsyncSession) -> TenantUser:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email="admin@acme.test",
        hashed_password=hash_password("correct-password"),
        full_name="Acme Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


async def test_create_tenant_creates_admin_user_and_sends_invite(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _create_super_admin(db)
    token = await _login(client, "root@reportai.dev", "super-secret-password")
    mock_send = AsyncMock()
    monkeypatch.setattr("app.api.admin.tenants.send_plain_email", mock_send)

    response = await client.post(
        "/admin/tenants",
        json={
            "name": "New Client",
            "slug": "new-client",
            "admin_email": "owner@new-client.test",
            "admin_full_name": "Owner Name",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "new-client"
    assert body["invite_email_sent"] is True
    mock_send.assert_awaited_once()

    result = await db.execute(
        select(TenantUser).where(TenantUser.email == "owner@new-client.test")
    )
    admin_user = result.scalar_one()
    assert admin_user.role == "tenant_admin"


async def test_create_tenant_placeholder_password_cannot_authenticate(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _create_super_admin(db)
    token = await _login(client, "root@reportai.dev", "super-secret-password")
    monkeypatch.setattr("app.api.admin.tenants.send_plain_email", AsyncMock())

    await client.post(
        "/admin/tenants",
        json={
            "name": "New Client",
            "slug": "new-client",
            "admin_email": "owner@new-client.test",
            "admin_full_name": "Owner Name",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    for guess in ("", "password", "owner@new-client.test", "new-client"):
        response = await client.post(
            "/auth/login", json={"email": "owner@new-client.test", "password": guess}
        )
        assert response.status_code == 401


async def test_create_tenant_duplicate_slug_conflicts(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _create_super_admin(db)
    token = await _login(client, "root@reportai.dev", "super-secret-password")
    monkeypatch.setattr("app.api.admin.tenants.send_plain_email", AsyncMock())
    payload = {
        "name": "New Client",
        "slug": "new-client",
        "admin_email": "owner@new-client.test",
        "admin_full_name": "Owner Name",
    }

    first = await client.post(
        "/admin/tenants", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert first.status_code == 201

    second = await client.post(
        "/admin/tenants",
        json={**payload, "admin_email": "someone-else@new-client.test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409


async def test_list_tenants_paginated(client: AsyncClient, db: AsyncSession) -> None:
    await _create_super_admin(db)
    token = await _login(client, "root@reportai.dev", "super-secret-password")
    for i in range(3):
        db.add(Tenant(name=f"Tenant {i}", slug=f"tenant-{i}", is_active=True))
    await db.commit()

    response = await client.get(
        "/admin/tenants?skip=0&limit=2", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_deactivate_tenant_toggles_is_active(client: AsyncClient, db: AsyncSession) -> None:
    await _create_super_admin(db)
    token = await _login(client, "root@reportai.dev", "super-secret-password")
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    response = await client.patch(
        f"/admin/tenants/{tenant.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_tenant_admin_forbidden_from_tenant_management(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _create_tenant_admin(db)
    token = await _login(client, "admin@acme.test", "correct-password")

    response = await client.get("/admin/tenants", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


async def test_tenants_endpoints_require_auth(client: AsyncClient) -> None:
    response = await client.get("/admin/tenants")

    assert response.status_code == 401
