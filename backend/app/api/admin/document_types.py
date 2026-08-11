import logging
import uuid
from pathlib import Path

from docxtpl import DocxTemplate
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ConflictException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.common import PaginatedResponse
from app.schemas.document_template import DocumentTemplateResponse
from app.schemas.document_type import (
    DocumentTypeCreateRequest,
    DocumentTypeResponse,
    DocumentTypeUpdateRequest,
    FieldSchemaEntry,
)

router = APIRouter(prefix="/document-types", tags=["admin:document-types"])
logger = logging.getLogger(__name__)


def _dump_field_schema(field_schema: dict[str, FieldSchemaEntry]) -> dict[str, object]:
    return {name: entry.model_dump() for name, entry in field_schema.items()}


@router.post("", status_code=201)
async def create_document_type(
    payload: DocumentTypeCreateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentTypeResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(DocumentType, db)
    try:
        doc_type = await repo.create(
            tenant_id=tenant_id,
            name=payload.name,
            description=payload.description,
            field_schema=_dump_field_schema(payload.field_schema),
            prompt_instructions=payload.prompt_instructions,
            notification_emails=payload.notification_emails,
            is_active=True,
        )
    except IntegrityError as exc:
        raise ConflictException(f"A document type named {payload.name!r} already exists") from exc
    return DocumentTypeResponse.model_validate(doc_type)


@router.get("")
async def list_document_types(
    skip: int = 0,
    limit: int = 100,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[DocumentTypeResponse]:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(DocumentType, db)
    filters = {"tenant_id": tenant_id}
    items = await repo.list(skip=skip, limit=limit, filters=filters)
    total = await repo.count(filters=filters)
    return PaginatedResponse(
        items=[DocumentTypeResponse.model_validate(d) for d in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{document_type_id}")
async def get_document_type(
    document_type_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentTypeResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(DocumentType, db)
    doc_type = await get_scoped_or_404(repo, document_type_id, tenant_id=tenant_id)
    return DocumentTypeResponse.model_validate(doc_type)


@router.patch("/{document_type_id}")
async def update_document_type(
    document_type_id: uuid.UUID,
    payload: DocumentTypeUpdateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentTypeResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(DocumentType, db)
    doc_type = await get_scoped_or_404(repo, document_type_id, tenant_id=tenant_id)
    try:
        doc_type = await repo.update(
            doc_type,
            name=payload.name,
            description=payload.description,
            field_schema=_dump_field_schema(payload.field_schema),
            prompt_instructions=payload.prompt_instructions,
            notification_emails=payload.notification_emails,
            is_active=payload.is_active,
        )
    except IntegrityError as exc:
        raise ConflictException(f"A document type named {payload.name!r} already exists") from exc
    return DocumentTypeResponse.model_validate(doc_type)


@router.post("/{document_type_id}/templates", status_code=201)
async def upload_template(
    document_type_id: uuid.UUID,
    file: UploadFile,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplateResponse:
    tenant_id = require_tenant_id(current_user)
    doc_type_repo = BaseRepository(DocumentType, db)
    doc_type = await get_scoped_or_404(doc_type_repo, document_type_id, tenant_id=tenant_id)

    storage_dir = Path(settings.DOCUMENT_STORAGE_PATH) / "templates" / str(tenant_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    dest = storage_dir / f"{uuid.uuid4()}.docx"
    dest.write_bytes(await file.read())

    try:
        template = DocxTemplate(str(dest))
        used_tags = template.get_undeclared_template_variables()
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ValidationException("The uploaded file isn't a valid .docx template") from exc

    unknown_tags = used_tags - set(doc_type.field_schema.keys())
    if unknown_tags:
        dest.unlink(missing_ok=True)
        raise ValidationException(
            f"Template references fields not in this document type's schema: {sorted(unknown_tags)}"
        )

    template_repo = BaseRepository(DocumentTemplate, db)
    existing = await template_repo.list(
        filters={"document_type_id": document_type_id, "is_active": True}, limit=1
    )
    next_version = 1
    if existing:
        prior = existing[0]
        next_version = prior.version + 1
        await template_repo.update(prior, is_active=False)

    new_template = await template_repo.create(
        tenant_id=tenant_id,
        document_type_id=document_type_id,
        file_path=str(dest),
        original_filename=file.filename or "template.docx",
        uploaded_by=current_user.id,
        version=next_version,
        is_active=True,
    )
    return DocumentTemplateResponse.model_validate(new_template)


@router.get("/{document_type_id}/templates")
async def list_templates(
    document_type_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[DocumentTemplateResponse]:
    tenant_id = require_tenant_id(current_user)
    doc_type_repo = BaseRepository(DocumentType, db)
    await get_scoped_or_404(doc_type_repo, document_type_id, tenant_id=tenant_id)

    repo = BaseRepository(DocumentTemplate, db)
    filters = {"document_type_id": document_type_id}
    items = await repo.list(skip=skip, limit=limit, filters=filters)
    total = await repo.count(filters=filters)
    return PaginatedResponse(
        items=[DocumentTemplateResponse.model_validate(t) for t in items],
        total=total,
        skip=skip,
        limit=limit,
    )
