"""scripts/seed_live_demo.py: the live demo's own company, account and document types, once."""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import can_sign_in
from app.core.security import hash_password
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from scripts.seed_live_demo import seed_live_demo

EMAIL = "live-demo@reportai.test"


async def test_it_sets_up_the_demo_company_once(
    db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "demo@reportai.test")

    ids = await seed_live_demo(db, EMAIL)
    await db.commit()

    account = await db.scalar(select(TenantUser).where(TenantUser.email == EMAIL))
    assert account is not None and account.tenant_id is not None and account.role == "tenant_admin"
    assert not await can_sign_in(db, account)  # nobody signs in, not even through a password reset
    tenant = await db.get(Tenant, account.tenant_id)
    assert tenant is not None and tenant.plan == "unlimited" and tenant.plan_status == "active"
    names = {}
    for language, document_type_id in ids.items():
        doc_type = await db.get(DocumentType, document_type_id)
        assert doc_type is not None and doc_type.tenant_id == tenant.id and doc_type.is_active
        names[language] = doc_type.name
        template = await db.scalar(
            select(DocumentTemplate).where(
                DocumentTemplate.document_type_id == doc_type.id, DocumentTemplate.is_active.is_(True)
            )
        )
        assert template is not None and Path(template.file_path).is_file()
    assert names == {"es": "Visita de seguridad y salud", "en": "Site safety inspection"}

    assert await seed_live_demo(db, EMAIL) == ids  # run again: nothing new
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == "live-demo")) == 1
    assert await db.scalar(select(func.count()).select_from(DocumentType).where(DocumentType.tenant_id == tenant.id)) == 2


async def test_it_refuses_the_one_click_demo_account(db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "Demo@reportai.test")
    with pytest.raises(SystemExit):
        await seed_live_demo(db, "demo@reportai.test")


async def test_it_refuses_an_address_of_another_company(db: AsyncSession) -> None:
    client = Tenant(name="Prevención Norte", slug="prevencion-norte")
    db.add(client)
    await db.flush()
    db.add(TenantUser(tenant_id=client.id, email=EMAIL, hashed_password=hash_password("pw-12345678"),
                      full_name="Marta", role="tenant_admin", is_active=True))
    await db.flush()

    with pytest.raises(SystemExit):
        await seed_live_demo(db, EMAIL)
    assert await db.scalar(select(func.count()).select_from(DocumentType).where(DocumentType.tenant_id == client.id)) == 0
