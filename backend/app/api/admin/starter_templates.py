"""Ready-made document types a company can start from (app/services/templates/starters.py)."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ResourceNotFoundException
from app.core.scoping import require_tenant_id
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.document_type import DocumentTypeResponse
from app.services.templates import starters
from app.services.templates.library import activate_template, new_template_path

router = APIRouter(prefix="/starter-templates", tags=["admin:starter-templates"])


class StarterResponse(BaseModel):
    key: str
    name: str
    description: str
    fields: list[str]


async def _language(db: AsyncSession, tenant_id: object) -> str:
    tenant = await db.get(Tenant, tenant_id)
    return tenant.language if tenant else "es"


@router.get("")
async def list_starters(
    current_user: TenantUser = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db)
) -> list[StarterResponse]:
    language = await _language(db, require_tenant_id(current_user))
    return [StarterResponse(**s) for s in starters.describe(language)]


@router.post("/{key}/install", status_code=201)
async def install_starter(
    key: str, current_user: TenantUser = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db)
) -> DocumentTypeResponse:
    """A new document type with the starter's fields and its template, ready for reports."""
    if key not in starters.STARTERS:
        raise ResourceNotFoundException("Unknown starter template")
    tenant_id = require_tenant_id(current_user)
    language = await _language(db, tenant_id)
    starter = starters.STARTERS[key]
    taken = set(await db.scalars(select(DocumentType.name).where(DocumentType.tenant_id == tenant_id)))
    name, n = starter.name[language], 2
    while name in taken:  # installed twice: "Parte de trabajo (2)"
        name, n = f"{starter.name[language]} ({n})", n + 1
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
        uploaded_by=current_user.id,
    )
    await db.refresh(doc_type)
    return DocumentTypeResponse.model_validate(doc_type)
