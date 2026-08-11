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
    assert response.status_code == 200
    return str(response.json()["access_token"])


_VALID_PAYLOAD = {
    "name": "Meeting Minutes",
    "description": "Internal meeting minutes",
    "field_schema": {
        "summary": {"type": "str", "description": "Summary", "required": True},
        "attendees": {"type": "list[str]", "description": "Attendees", "required": False},
    },
    "prompt_instructions": "Extract meeting fields.",
    "notification_emails": ["reports@acme.test"],
}


async def test_create_document_type(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)

    response = await client.post(
        "/document-types", json=_VALID_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Meeting Minutes"
    assert body["notification_emails"] == ["reports@acme.test"]
    assert body["field_schema"]["summary"]["type"] == "str"


async def test_create_document_type_rejects_unsupported_field_type(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    payload = {**_VALID_PAYLOAD, "field_schema": {"x": {"type": "not-a-real-type"}}}

    response = await client.post(
        "/document-types", json=payload, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 422


async def test_create_document_type_duplicate_name_conflicts(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.post("/document-types", json=_VALID_PAYLOAD, headers=headers)
    assert first.status_code == 201

    second = await client.post("/document-types", json=_VALID_PAYLOAD, headers=headers)
    assert second.status_code == 409


async def test_get_document_type_cross_tenant_returns_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await _create_tenant_admin(db, name="Acme", slug="acme")
    other = await _create_tenant_admin(db, name="Other Co", slug="other")
    owner_token = await _login(client, owner.email)
    other_token = await _login(client, other.email)

    create_response = await client.post(
        "/document-types", json=_VALID_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"}
    )
    doc_type_id = create_response.json()["id"]

    response = await client.get(
        f"/document-types/{doc_type_id}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404


async def test_update_document_type_round_trips_notification_emails(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post("/document-types", json=_VALID_PAYLOAD, headers=headers)
    doc_type_id = create_response.json()["id"]

    update_payload = {**_VALID_PAYLOAD, "notification_emails": ["a@acme.test", "b@acme.test"]}
    response = await client.patch(
        f"/document-types/{doc_type_id}", json=update_payload, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["notification_emails"] == ["a@acme.test", "b@acme.test"]
