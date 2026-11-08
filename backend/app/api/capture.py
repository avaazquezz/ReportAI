"""The app's way in: a technician (or an approver) records a report in the browser. It enters the
same pipeline as a chat message, minus the chat: the document type is chosen before recording,
and the person reviews and confirms the result on screen (approve / reply in api/admin/reports.py)."""

import asyncio
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_capturer
from app.core.exceptions import ConflictException, PlanLimitException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.document_template import DocumentTemplate
from app.models.document_type import DocumentType
from app.models.report import Report
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.services import plans
from app.services.agent.ingestion import create_report_with_job, store_photo
from app.services.channels.web import WEB, store_voice_note, web_connection
from app.services.i18n import t

router = APIRouter(tags=["capture"])

MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # a phone camera's full-size picture; it is downsized on save


class CaptureResponse(BaseModel):
    id: uuid.UUID
    status: str


class CaptureDocumentType(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None


def _replay(report: Report, user: TenantUser) -> CaptureResponse:
    """The same capture sent again (the app retries until it hears back): the report it made."""
    if report.tenant_id != user.tenant_id or report.requester_user_id != user.id:
        raise ConflictException("That Idempotency-Key belongs to another report")
    return CaptureResponse(id=report.id, status=report.status)


def _check_photo(raw: bytes) -> None:
    with Image.open(io.BytesIO(raw)) as image:
        image.verify()


@router.get("/capture/document-types")
async def capture_document_types(
    current_user: TenantUser = Depends(require_capturer), db: AsyncSession = Depends(get_db)
) -> list[CaptureDocumentType]:
    """What the app offers to record: the company's active types that have a template (one without
    would spend the extraction and then fail to render). Just the picker's fields: a technician
    has no business with the prompts or the recipients."""
    has_template = exists().where(DocumentTemplate.document_type_id == DocumentType.id, DocumentTemplate.is_active.is_(True))
    types = await db.scalars(
        select(DocumentType)
        .where(DocumentType.tenant_id == require_tenant_id(current_user), DocumentType.is_active.is_(True), has_template)
        .order_by(DocumentType.name)
    )
    return [CaptureDocumentType(id=dt.id, name=dt.name, description=dt.description) for dt in types]


@router.post("/capture", status_code=202)
async def capture_report(
    document_type_id: Annotated[uuid.UUID, Form()],
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    text: Annotated[str | None, Form(max_length=20_000)] = None,
    audio: Annotated[UploadFile | None, File()] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
    current_user: TenantUser = Depends(require_capturer),
    db: AsyncSession = Depends(get_db),
) -> CaptureResponse:
    """Starts a report from a voice note and/or a typed note, with its photos. The Idempotency-Key
    (a UUID the app makes before the first try) becomes the report's id, so a retry after a lost
    answer returns the same report instead of a second one."""
    tenant_id = require_tenant_id(current_user)
    if (existing := await db.get(Report, idempotency_key)) is not None:
        return _replay(existing, current_user)

    document_type = await get_scoped_or_404(BaseRepository(DocumentType, db), document_type_id, tenant_id=tenant_id)
    if not document_type.is_active:
        raise ValidationException("That document type is switched off")
    text = (text or "").strip() or None
    if audio is None and text is None:
        raise ValidationException("Record a voice note or type the report")
    photos = photos or []
    if len(photos) > MAX_PHOTOS:
        raise ValidationException(f"At most {MAX_PHOTOS} photos per report")

    tenant = await db.get(Tenant, tenant_id)
    if refusal := await plans.message_refusal(db, tenant, voice=audio is not None):
        raise PlanLimitException(t(tenant.language if tenant else None, refusal))
    assert tenant is not None  # message_refusal refuses a missing company
    if refusal := await plans.new_report_refusal(db, tenant):
        raise PlanLimitException(t(tenant.language, refusal))

    # Every file is checked before anything is stored, so a bad photo leaves nothing behind.
    pictures: list[bytes] = []
    for photo in photos:
        raw = await photo.read(MAX_PHOTO_BYTES + 1)
        if len(raw) > MAX_PHOTO_BYTES:
            raise ValidationException(f"A photo is over the {MAX_PHOTO_BYTES // (1024 * 1024)} MB limit")
        try:
            await asyncio.to_thread(_check_photo, raw)
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:  # what Pillow raises for a non-image
            raise ValidationException(f"{photo.filename or 'A photo'} is not a picture") from exc
        pictures.append(raw)
    media_reference = await store_voice_note(audio) if audio is not None else None

    connection = await web_connection(db, tenant_id)
    sender_id = str(current_user.id)
    report = await create_report_with_job(
        db,
        connection,
        report_id=idempotency_key,
        sender_id=sender_id,
        channel_type=WEB,
        text=text,
        media_reference=media_reference,
        sender_label=current_user.full_name,
        requester_user_id=current_user.id,
        document_type_id=document_type.id,
    )
    if report is None:  # the same capture, sent twice at once: the other one is making it
        if (replayed := await db.get(Report, idempotency_key)) is None:
            raise ConflictException("This capture is already being saved. Try again in a moment.")
        return _replay(replayed, current_user)
    for raw in pictures:
        await store_photo(db, tenant_id=tenant_id, report_id=report.id, sender_id=sender_id, raw=raw)
    return CaptureResponse(id=report.id, status=report.status)
