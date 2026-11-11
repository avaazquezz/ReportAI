"""Ready-made document types a company can start from (app/services/templates/starters.py)."""

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
from app.services.templates import library, starters

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
    doc_type = await library.install_starter(
        db, tenant_id=tenant_id, key=key, language=language, name=name, uploaded_by=current_user.id
    )
    return DocumentTypeResponse.model_validate(doc_type)
