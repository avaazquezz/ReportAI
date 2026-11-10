"""Where a document type's templates live, and how a new one becomes the active version."""

import asyncio
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.repositories.base import BaseRepository
from app.services.templates import starters


def new_template_path(tenant_id: uuid.UUID) -> Path:
    folder = Path(settings.DOCUMENT_STORAGE_PATH) / "templates" / str(tenant_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4()}.docx"


async def activate_template(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_type_id: uuid.UUID,
    file_path: str,
    original_filename: str,
    uploaded_by: uuid.UUID | None,
) -> DocumentTemplate:
    """The new template is what reports render with from now on; earlier versions stay listed."""
    repo = BaseRepository(DocumentTemplate, db)
    active = await repo.list(filters={"document_type_id": document_type_id, "is_active": True}, limit=1)
    version = 1
    if active:
        version = active[0].version + 1
        await repo.update(active[0], is_active=False)
    return await repo.create(
        tenant_id=tenant_id,
        document_type_id=document_type_id,
        file_path=file_path,
        original_filename=original_filename,
        uploaded_by=uploaded_by,
        version=version,
        is_active=True,
    )


async def install_starter(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    key: str,
    language: str,
    name: str,
    uploaded_by: uuid.UUID | None,
) -> DocumentType:
    """A new document type with the starter's fields and its template, ready for reports."""
    starter = starters.STARTERS[key]
    path = new_template_path(tenant_id)
    field_schema = await asyncio.to_thread(starters.build, key, language, str(path))
    doc_type = DocumentType(
        tenant_id=tenant_id,
        name=name,
        description=starter.description[language],
        field_schema=field_schema,
        prompt_instructions=starter.instructions[language],
        notification_emails=[],
        is_active=True,
    )
    db.add(doc_type)
    await db.flush()
    await activate_template(
        db,
        tenant_id=tenant_id,
        document_type_id=doc_type.id,
        file_path=str(path),
        original_filename=f"{name}.docx",
        uploaded_by=uploaded_by,
    )
    await db.refresh(doc_type)
    return doc_type
