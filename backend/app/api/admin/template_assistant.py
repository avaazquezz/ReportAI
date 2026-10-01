"""The template assistant in the panel: upload a filled-in example, correct what was proposed,
look at a test render, apply. See app/services/templates/assistant.py."""

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.document_type import DocumentTypeResponse
from app.services.branding import Branding
from app.services.instance_settings import NotConfiguredError
from app.services.rendering.gotenberg_client import convert_docx_to_pdf
from app.services.templates import assistant
from app.services.templates.assistant import Draft, PlanError, Proposal
from app.services.templates.library import activate_template, new_template_path

router = APIRouter(prefix="/document-types", tags=["admin:template-assistant"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class PreviewRequest(BaseModel):
    proposal: Proposal
    # labels: each field shows its name where it goes; example: the example's own values.
    mode: Literal["labels", "example"] = "labels"


async def _context(
    db: AsyncSession, user: TenantUser, document_type_id: uuid.UUID
) -> tuple[uuid.UUID, DocumentType, Tenant]:
    tenant_id = require_tenant_id(user)
    doc_type = await get_scoped_or_404(BaseRepository(DocumentType, db), document_type_id, tenant_id=tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    assert tenant is not None
    return tenant_id, doc_type, tenant


def _draft(tenant_id: uuid.UUID, document_type_id: uuid.UUID, draft_id: uuid.UUID) -> Draft:
    draft = assistant.load_draft(tenant_id, draft_id)
    if draft is None or draft.document_type_id != document_type_id:
        raise ResourceNotFoundException("This upload expired or doesn't exist: upload the document again")
    return draft


@router.post("/{document_type_id}/template-assistant", status_code=201)
async def analyze_example(
    document_type_id: uuid.UUID,
    file: UploadFile,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> Draft:
    """Reads a filled-in example and proposes the fields and where each one goes."""
    tenant_id, doc_type, tenant = await _context(db, current_user, document_type_id)
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationException("The document must be under 15 MB")
    try:
        return await assistant.create_draft(
            tenant_id=tenant_id,
            document_type_id=doc_type.id,
            filename=file.filename or "template.docx",
            content=content,
            language=tenant.language,
        )
    except (PlanError, NotConfiguredError) as exc:
        raise ValidationException(str(exc)) from exc


@router.post("/{document_type_id}/template-assistant/{draft_id}/preview")
async def preview_template(
    document_type_id: uuid.UUID,
    draft_id: uuid.UUID,
    payload: PreviewRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """A test render as PDF, with the proposal as it stands — nothing is saved."""
    tenant_id, _, tenant = await _context(db, current_user, document_type_id)
    draft = _draft(tenant_id, document_type_id, draft_id)
    with tempfile.TemporaryDirectory() as folder:
        try:
            docx = await asyncio.to_thread(
                assistant.preview_docx, tenant_id, draft, payload.proposal, payload.mode, Branding.of(tenant), folder
            )
        except PlanError as exc:
            raise ValidationException(str(exc)) from exc
        pdf = await convert_docx_to_pdf(docx, f"{folder}/preview.pdf")
        content = Path(pdf).read_bytes()
    return Response(content=content, media_type="application/pdf")


@router.post("/{document_type_id}/template-assistant/{draft_id}/apply")
async def apply_template(
    document_type_id: uuid.UUID,
    draft_id: uuid.UUID,
    payload: Proposal,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> DocumentTypeResponse:
    """Builds the template from the example, adds its fields to the document type and makes it
    the template reports render with."""
    tenant_id, doc_type, _ = await _context(db, current_user, document_type_id)
    draft = _draft(tenant_id, document_type_id, draft_id)
    destination = new_template_path(tenant_id)
    try:
        await asyncio.to_thread(assistant.build_template, tenant_id, draft, payload, str(destination))
    except PlanError as exc:
        destination.unlink(missing_ok=True)
        raise ValidationException(str(exc)) from exc
    doc_type.field_schema = assistant.merged_schema(doc_type.field_schema, payload)
    await activate_template(
        db,
        tenant_id=tenant_id,
        document_type_id=doc_type.id,
        file_path=str(destination),
        original_filename=draft.filename,
        uploaded_by=current_user.id,
    )
    await db.flush()
    await db.refresh(doc_type)
    assistant.drop_draft(tenant_id, draft.id)
    return DocumentTypeResponse.model_validate(doc_type)
