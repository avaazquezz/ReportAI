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


async def test_demo_login_404_when_not_configured(client: AsyncClient) -> None:
    response = await client.post("/auth/demo-login")

    assert response.status_code == 404


async def test_demo_login_returns_working_readonly_session(
    client: AsyncClient, db: AsyncSession, monkeypatch
) -> None:
    from app.core.config import settings

    await _create_user(db)
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "user@acme.test")

    login = await client.post("/auth/demo-login")
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["is_demo"] is True

    # Reads work, writes are blocked by the single guard in get_current_user.
    reads = await client.get("/channels", headers=headers)
    assert reads.status_code == 200
    write = await client.post(
        "/channels",
        headers=headers,
        json={
            "channel_type": "telegram",
            "display_name": "x",
            "credentials": {"bot_token": "t"},
            "allowed_senders": [],
        },
    )
    assert write.status_code == 403
