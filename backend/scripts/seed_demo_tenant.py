"""Seeds a demo tenant with a self-generated document template — no manual asset creation.
Idempotent: safe to run repeatedly, does nothing if the demo tenant already exists.

Usage: make seed-demo
"""

import asyncio
import uuid
from pathlib import Path

from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.channel_connection import ChannelConnection
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository

DEMO_USER_EMAIL = "demo@reportai.dev"
DEMO_USER_PASSWORD = "DemoPass123!"

FIELD_SCHEMA = {
    "meeting_date": {"type": "date", "description": "Date the meeting took place, ISO 8601", "required": True},
    "attendees": {"type": "list[str]", "description": "Full names of attendees", "required": True},
    "summary": {"type": "str", "description": "One-paragraph summary of the meeting", "required": True},
    "action_items": {"type": "list[str]", "description": "Agreed action items", "required": False},
}


def _generate_template(output_path: Path) -> None:
    """Builds a valid docxtpl target with zero manual asset creation — every field_schema
    key becomes a {{ jinja_tag }} written as plain paragraph text."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    document.add_heading("Meeting Minutes", level=1)
    document.add_paragraph("Date: {{ meeting_date }}")
    document.add_paragraph("Attendees: {% for a in attendees %}{{ a }}{% if not loop.last %}, {% endif %}{% endfor %}")
    document.add_heading("Summary", level=2)
    document.add_paragraph("{{ summary }}")
    document.add_heading("Action items", level=2)
    document.add_paragraph("{% for item in action_items %}- {{ item }}\n{% endfor %}")
    document.save(str(output_path))


async def _ensure_demo_user(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    user_repo = BaseRepository(TenantUser, session)
    existing = await user_repo.list(filters={"email": DEMO_USER_EMAIL}, limit=1)
    if existing:
        return
    await user_repo.create(
        tenant_id=tenant_id,
        email=DEMO_USER_EMAIL,
        hashed_password=hash_password(DEMO_USER_PASSWORD),
        full_name="Demo Admin",
        role="tenant_admin",
        is_active=True,
    )
    await session.commit()
    print(f"Demo login: {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}")


async def seed_demo_tenant() -> None:
    async with AsyncSessionLocal() as session:
        tenant_repo = BaseRepository(Tenant, session)
        existing = await tenant_repo.list(filters={"slug": "demo"}, limit=1)
        if existing:
            print("Demo tenant already exists — checking demo user.")
            await _ensure_demo_user(session, existing[0].id)
            return

        tenant = await tenant_repo.create(name="Demo Consulting S.L.", slug="demo", is_active=True)

        doc_type_repo = BaseRepository(DocumentType, session)
        document_type = await doc_type_repo.create(
            tenant_id=tenant.id,
            name="Meeting Minutes",
            description="Internal meeting minutes",
            field_schema=FIELD_SCHEMA,
            prompt_instructions="Extract meeting minutes fields from an internal company meeting transcript.",
            notification_emails=["demo-reports@example.com"],
            is_active=True,
        )

        template_path = Path(settings.DOCUMENT_STORAGE_PATH) / "templates" / "demo_meeting_minutes.docx"
        _generate_template(template_path)

        template_repo = BaseRepository(DocumentTemplate, session)
        await template_repo.create(
            tenant_id=tenant.id,
            document_type_id=document_type.id,
            file_path=str(template_path),
            version=1,
            is_active=True,
        )

        connection_repo = BaseRepository(ChannelConnection, session)
        await connection_repo.create(
            tenant_id=tenant.id,
            channel_type="telegram",
            display_name="Demo Telegram Bot",
            credentials={"bot_token": "TEST_TOKEN_NOT_REAL_REPLACE_BEFORE_USE"},
            is_active=True,
        )

        await session.commit()
        print(f"Seeded demo tenant {tenant.id} with document type {document_type.id}.")
        print("Replace the fake bot_token in channel_connections before sending real messages.")

        await _ensure_demo_user(session, tenant.id)


if __name__ == "__main__":
    asyncio.run(seed_demo_tenant())
