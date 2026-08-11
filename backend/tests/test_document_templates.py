import io

from docx import Document
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser

_FIELD_SCHEMA = {
    "meeting_date": {"type": "date", "description": "Date", "required": True},
    "summary": {"type": "str", "description": "Summary", "required": True},
}


async def _create_tenant_admin(db: AsyncSession) -> TenantUser:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email="admin@acme.test",
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


async def _create_document_type(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/document-types",
        json={"name": "Meeting Minutes", "field_schema": _FIELD_SCHEMA},
        headers=headers,
    )
    return str(response.json()["id"])


def _build_docx(tags: list[str]) -> bytes:
    document = Document()
    for tag in tags:
        document.add_paragraph(f"{{{{ {tag} }}}}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_upload_valid_template_succeeds(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    doc_type_id = await _create_document_type(client, headers)

    response = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers=headers,
        files={"file": ("template.docx", _build_docx(["meeting_date", "summary"]), "application/octet-stream")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "template.docx"
    assert body["version"] == 1
    assert body["is_active"] is True


async def test_upload_corrupt_file_rejected(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    doc_type_id = await _create_document_type(client, headers)

    response = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers=headers,
        files={"file": ("template.docx", b"not a real docx file", "application/octet-stream")},
    )

    assert response.status_code == 400


async def test_upload_template_with_unknown_tags_rejected(client: AsyncClient, db: AsyncSession) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    doc_type_id = await _create_document_type(client, headers)

    response = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers=headers,
        files={
            "file": (
                "template.docx",
                _build_docx(["meeting_date", "summary", "not_a_real_field"]),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400
    assert "not_a_real_field" in response.json()["detail"]


async def test_reupload_increments_version_and_deactivates_prior(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await _create_tenant_admin(db)
    token = await _login(client, user.email)
    headers = {"Authorization": f"Bearer {token}"}
    doc_type_id = await _create_document_type(client, headers)

    first = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers=headers,
        files={"file": ("v1.docx", _build_docx(["meeting_date", "summary"]), "application/octet-stream")},
    )
    second = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers=headers,
        files={"file": ("v2.docx", _build_docx(["summary"]), "application/octet-stream")},
    )

    assert second.json()["version"] == 2

    history = await client.get(f"/document-types/{doc_type_id}/templates", headers=headers)
    versions = {item["id"]: item["is_active"] for item in history.json()["items"]}
    assert versions[first.json()["id"]] is False
    assert versions[second.json()["id"]] is True


async def test_upload_template_cross_tenant_returns_404(client: AsyncClient, db: AsyncSession) -> None:
    owner = await _create_tenant_admin(db)
    owner_token = await _login(client, owner.email)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    doc_type_id = await _create_document_type(client, owner_headers)

    other_tenant = Tenant(name="Other Co", slug="other", is_active=True)
    db.add(other_tenant)
    await db.flush()
    other_user = TenantUser(
        tenant_id=other_tenant.id,
        email="admin@other.test",
        hashed_password=hash_password("correct-password"),
        full_name="Other Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(other_user)
    await db.commit()
    other_token = await _login(client, other_user.email)

    response = await client.post(
        f"/document-types/{doc_type_id}/templates",
        headers={"Authorization": f"Bearer {other_token}"},
        files={"file": ("template.docx", _build_docx(["summary"]), "application/octet-stream")},
    )

    assert response.status_code == 404
