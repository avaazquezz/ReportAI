"""The company's own settings — name, language, clock, logo and colour — and its look on what
ReportAI sends for it: branded emails, and {{ branding.* }} in its documents."""

import io
import uuid
import zipfile
from email import message_from_bytes
from email.header import decode_header, make_header
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from docx import Document
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.branding import Branding
from app.services.delivery import email as smtp_delivery
from app.services.rendering.docx_render import fill_template


async def _person(db: AsyncSession, role: str = "tenant_admin") -> TenantUser:
    tenant = Tenant(name="Reformas García", slug=f"garcia-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id, email=f"{uuid.uuid4().hex[:6]}@garcia.test", hashed_password=hash_password("pw-12345678"),
        full_name="Lucía", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _headers(client: AsyncClient, user: TenantUser) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": user.email, "password": "pw-12345678"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _png(color: str = "red", size: tuple[int, int] = (1200, 400)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def _storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))


async def test_the_admin_edits_the_company_and_everyone_reads_it(client: AsyncClient, db: AsyncSession) -> None:
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)

    updated = await client.patch(
        "/company",
        json={"name": "Reformas García S.L.", "language": "en", "timezone": "Atlantic/Canary", "brand_color": "#0a7c66"},
        headers=admin,
    )

    assert updated.json() == {
        "name": "Reformas García S.L.", "language": "en", "timezone": "Atlantic/Canary", "brand_color": "#0A7C66", "has_logo": False,
    }
    bad = await client.patch("/company", json={"name": "X", "language": "en", "timezone": "Mars/Base"}, headers=admin)
    assert bad.status_code == 422


async def test_only_the_admin_changes_it(client: AsyncClient, db: AsyncSession) -> None:
    viewer = await _headers(client, await _person(db, "viewer"))

    assert (await client.get("/company", headers=viewer)).status_code == 200
    assert (await client.patch("/company", json={"name": "X", "language": "es", "timezone": "Europe/Madrid"}, headers=viewer)).status_code == 403


async def test_a_logo_is_kept_as_a_small_png_and_replaced_cleanly(client: AsyncClient, db: AsyncSession) -> None:
    admin_user = await _person(db)
    admin = await _headers(client, admin_user)

    first = await client.put("/company/logo", files={"file": ("logo.jpg", _png(), "image/jpeg")}, headers=admin)
    assert first.json()["has_logo"] is True
    tenant = await db.get(Tenant, admin_user.tenant_id)
    await db.refresh(tenant)
    assert tenant is not None and tenant.logo_path
    old_path = tenant.logo_path
    with Image.open(old_path) as stored:
        assert stored.format == "PNG" and max(stored.size) <= 800

    served = await client.get("/company/logo", headers=admin)
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"

    await client.put("/company/logo", files={"file": ("logo.png", _png("blue"), "image/png")}, headers=admin)
    assert not Path(old_path).exists()  # the replaced logo doesn't linger on disk

    refused = await client.put("/company/logo", files={"file": ("logo.txt", b"not an image", "text/plain")}, headers=admin)
    assert refused.status_code == 400

    removed = await client.delete("/company/logo", headers=admin)
    assert removed.json()["has_logo"] is False
    assert (await client.get("/company/logo", headers=admin)).status_code == 404


async def test_report_emails_carry_the_companys_name_colour_and_logo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = AsyncMock()
    monkeypatch.setattr(smtp_delivery.aiosmtplib, "send", send)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_FROM_ADDRESS", "informes@garcia.test")
    logo = tmp_path / "logo.png"
    Image.new("RGB", (100, 40), "red").save(logo)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    await smtp_delivery.send_report_email(
        to=["jefe@garcia.test"], subject="Visita", body="Adjunto el informe.\nhttps://example.test/x",
        attachment_path=str(pdf), branding=Branding(name="Reformas García", color="#0A7C66", logo_path=str(logo)),
    )

    sent = message_from_bytes(send.await_args.args[0].as_bytes())
    assert str(make_header(decode_header(sent["From"]))) == "Reformas García <informes@garcia.test>"
    html = next(part for part in sent.walk() if part.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert "#0A7C66" in html and "cid:" in html and 'href="https://example.test/x"' in html
    assert any(part.get_content_type() == "image/png" for part in sent.walk())
    assert any(part.get_content_type() == "application/pdf" for part in sent.walk())
    assert next(p for p in sent.walk() if p.get_content_type() == "text/plain").get_payload(decode=True).decode().startswith("Adjunto")


def test_templates_can_show_the_company_name_and_logo(tmp_path: Path) -> None:
    template = tmp_path / "template.docx"
    document = Document()
    document.add_paragraph("{{ branding.logo }}")
    document.add_paragraph("Informe de {{ branding.name }} para {{ client }}")
    document.save(str(template))
    logo = tmp_path / "logo.png"
    Image.new("RGB", (300, 100), "red").save(logo)

    out = fill_template(
        str(template), {"client": "Acme"}, str(tmp_path / "out.docx"),
        branding=Branding(name="Reformas García", color="#C0432A", logo_path=str(logo)),
    )

    text = "\n".join(p.text for p in Document(out).paragraphs)
    assert "Informe de Reformas García para Acme" in text
    assert any(name.startswith("word/media/") for name in zipfile.ZipFile(out).namelist())


async def test_branding_is_not_a_field_name(client: AsyncClient, db: AsyncSession) -> None:
    admin = await _headers(client, await _person(db))

    response = await client.post(
        "/document-types", json={"name": "Visita", "field_schema": {"branding": {"type": "str"}}}, headers=admin
    )

    assert response.status_code == 422
