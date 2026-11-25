"""Short-lived download links for a report's PDF, which the MCP server gives an assistant so the
person on the other end can download the document from any client: an AI client may not pass on a
PDF embedded in a tool result, or only a small one.

The link is a sealed token (app/core/crypto.py: encrypted, unalterable, dated) that names the report
and the API key that asked for it. It is checked again when it is opened, so it is never worth more
than that key is then: revoking the key, or switching its person off, kills it at once, and it
reaches only a report the key's person can still see. It lasts ten minutes, so one copied into a
chat or a log is soon worth nothing.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.reports import visible_report
from app.core.config import settings
from app.core.crypto import seal, unseal
from app.core.database import get_db
from app.core.exceptions import ResourceNotFoundException
from app.services import api_keys
from app.services.delivery.deliveries import report_pdf_name

PDF_LINK_TTL = timedelta(minutes=10)
# Every sealed link shares one key, so a token made for something else (a signup link) must not pass.
_PURPOSE = "report_pdf"
_GONE = "This download link is wrong or has expired: ask your assistant for the PDF again"

router = APIRouter(prefix="/pdf-links", tags=["reports"])


def pdf_link(report_id: uuid.UUID, key_id: uuid.UUID) -> str:
    # Every installation serves the API under its panel's origin (Traefik on the hosted service,
    # Caddy on a server of its own); only in development is the API on a port of its own.
    token = seal({"purpose": _PURPOSE, "report": str(report_id), "key": str(key_id)})
    return f"{settings.FRONTEND_ORIGIN}{settings.API_ROOT_PATH}{router.prefix}/{token}"


@router.get("/{token}")
async def download_by_link(token: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    try:
        claims = unseal(token, PDF_LINK_TTL)
    except ValueError as exc:
        raise ResourceNotFoundException(_GONE) from exc
    if claims.get("purpose") != _PURPOSE:
        raise ResourceNotFoundException(_GONE)
    user = await api_keys.person_of(db, uuid.UUID(claims["key"]))
    if user is None:
        raise ResourceNotFoundException(_GONE)
    try:
        report = await visible_report(db, uuid.UUID(claims["report"]), user)
    except ResourceNotFoundException as exc:  # one answer for every dead link
        raise ResourceNotFoundException(_GONE) from exc
    if not report.file_path:
        raise ResourceNotFoundException(_GONE)
    return FileResponse(
        report.file_path,
        filename=await report_pdf_name(db, report),
        media_type="application/pdf",
        # The link is a credential while it lasts: no cache keeps the file, no page it leads to
        # learns the address.
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
