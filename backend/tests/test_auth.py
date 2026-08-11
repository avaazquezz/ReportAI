from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


async def _create_user(db: AsyncSession, *, is_active: bool = True) -> None:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(
        TenantUser(
            tenant_id=tenant.id,
            email="user@acme.test",
            hashed_password=hash_password("correct-password"),
            full_name="Test User",
            role="tenant_admin",
            is_active=is_active,
        )
    )
    await db.commit()


async def test_login_succeeds_with_correct_credentials(client: AsyncClient, db: AsyncSession) -> None:
    await _create_user(db)

    response = await client.post(
        "/auth/login", json={"email": "user@acme.test", "password": "correct-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_rejects_wrong_password(client: AsyncClient, db: AsyncSession) -> None:
    await _create_user(db)

    response = await client.post(
        "/auth/login", json={"email": "user@acme.test", "password": "wrong-password"}
    )

    assert response.status_code == 401


async def test_login_rejects_unknown_email(client: AsyncClient, db: AsyncSession) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@acme.test", "password": "correct-password"}
    )

    assert response.status_code == 401


async def test_login_rejects_inactive_user(client: AsyncClient, db: AsyncSession) -> None:
    await _create_user(db, is_active=False)

    response = await client.post(
        "/auth/login", json={"email": "user@acme.test", "password": "correct-password"}
    )

    assert response.status_code == 401


async def test_me_returns_current_user_with_valid_token(client: AsyncClient, db: AsyncSession) -> None:
    await _create_user(db)
    login_response = await client.post(
        "/auth/login", json={"email": "user@acme.test", "password": "correct-password"}
    )
    token = login_response.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@acme.test"
    assert body["role"] == "tenant_admin"


async def test_me_rejects_missing_token(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401
