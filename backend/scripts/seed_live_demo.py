"""Sets up the company the landing's live demo works in (app/api/public_demo.py): a company of its
own, the account PUBLIC_DEMO_USER_EMAIL names and the health-and-safety visit starter in Spanish
and English. Idempotent: run again, it reuses what is there. It prints the two document type ids
to put in PUBLIC_DEMO_DOCUMENT_TYPE_ES / _EN before setting PUBLIC_DEMO_ENABLED=true.

Usage: python scripts/seed_live_demo.py   (in the backend container, with PUBLIC_DEMO_USER_EMAIL set)

Nobody can sign into that account: it is created switched off (can_sign_in refuses it on every way
in, a password reset included), and the demo doesn't need it on. That company holds every visitor's
recording of the last day, so the script only ever works in the company it created itself."""

import asyncio
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services.templates import library, starters

STARTER = "safety_visit"
LANGUAGES = ("es", "en")
SLUG = "live-demo"


async def seed_live_demo(db: AsyncSession, email: str) -> dict[str, uuid.UUID]:
    """The live demo's document type id per language, creating whatever is missing (no commit)."""
    if settings.DEMO_USER_EMAIL and email.strip().lower() == settings.DEMO_USER_EMAIL.strip().lower():
        raise SystemExit("PUBLIC_DEMO_USER_EMAIL must not be DEMO_USER_EMAIL: anyone can sign into that company")
    account = await db.scalar(select(TenantUser).where(TenantUser.email == email))
    if account is None:
        # "unlimited": its reports count towards its quota until the purge deletes them a day later.
        tenant = Tenant(name="ReportAI · demo en vivo", slug=SLUG, plan="unlimited")
        db.add(tenant)
        await db.flush()
        account = TenantUser(
            tenant_id=tenant.id,
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name="Demo en vivo",
            role="tenant_admin",
            is_active=False,
        )
        db.add(account)
        await db.flush()
    company = await db.get(Tenant, account.tenant_id) if account.tenant_id else None
    if company is None or company.slug != SLUG:
        raise SystemExit(
            f"{email} already belongs to another company (or is a super admin): pick an address of its own "
            "for PUBLIC_DEMO_USER_EMAIL, or visitors' recordings would land in that company"
        )

    ids: dict[str, uuid.UUID] = {}
    for language in LANGUAGES:
        name = starters.STARTERS[STARTER].name[language]
        doc_type = await db.scalar(
            select(DocumentType).where(DocumentType.tenant_id == company.id, DocumentType.name == name)
        )
        if doc_type is None:
            doc_type = await library.install_starter(
                db, tenant_id=company.id, key=STARTER, language=language, name=name, uploaded_by=account.id
            )
        ids[language] = doc_type.id
    return ids


async def main() -> None:
    if not settings.PUBLIC_DEMO_USER_EMAIL:
        raise SystemExit("Set PUBLIC_DEMO_USER_EMAIL first: the live demo works in that account's company")
    async with AsyncSessionLocal() as db:
        ids = await seed_live_demo(db, settings.PUBLIC_DEMO_USER_EMAIL)
        await db.commit()
    for language, document_type_id in ids.items():
        print(f"PUBLIC_DEMO_DOCUMENT_TYPE_{language.upper()}={document_type_id}")


if __name__ == "__main__":
    asyncio.run(main())
