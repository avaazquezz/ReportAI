from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


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


async def test_create_telegram_connection(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    response = await client.post(
        "/channels",
        json={
            "channel_type": "telegram",
            "display_name": "Support Bot",
            "credentials": {"bot_token": "secret-token"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["has_credentials"] is True
    assert "bot_token" not in body
    assert "credentials" not in body


async def test_create_connection_missing_required_credential_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    response = await client.post(
        "/channels",
        json={"channel_type": "whatsapp", "display_name": "WA", "credentials": {"access_token": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_get_connection_never_exposes_raw_credentials(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    create_response = await client.post(
        "/channels",
        json={
            "channel_type": "telegram",
            "display_name": "Bot",
            "credentials": {"bot_token": "super-secret"},
        },
        headers=headers,
    )
    connection_id = create_response.json()["id"]

    response = await client.get(f"/channels/{connection_id}", headers=headers)

    assert "super-secret" not in response.text


async def test_update_merges_credentials_without_full_resupply(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    create_response = await client.post(
        "/channels",
        json={
            "channel_type": "whatsapp",
            "display_name": "WA",
            "credentials": {"phone_number_id": "123", "access_token": "original-token"},
        },
        headers=headers,
    )
    connection_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/channels/{connection_id}",
        json={"display_name": "WA Updated", "credentials": {"access_token": "rotated-token"}},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "WA Updated"
    assert update_response.json()["has_credentials"] is True


async def test_channel_connection_cross_tenant_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    owner_token = await _login(client, owner.email)
    other_token = await _login(client, other.email)

    create_response = await client.post(
        "/channels",
        json={"channel_type": "telegram", "display_name": "Bot", "credentials": {"bot_token": "x"}},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    connection_id = create_response.json()["id"]

    response = await client.get(
        f"/channels/{connection_id}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404
