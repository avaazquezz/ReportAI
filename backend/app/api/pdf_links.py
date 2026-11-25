"""Short-lived download links for a report's PDF, which the MCP server gives an assistant so the
person on the other end can download the document from any client: an AI client may not pass on a
PDF embedded in a tool result, or only a small one.

The link is a sealed token (app/core/crypto.py: encrypted, unalterable, dated) that names the report
and the credential that asked for it (an API key, or a connected app's grant). It is checked again
when it is opened, so it is never worth more than that credential is then: revoking it, or switching
its person off, kills it at once, and it reaches only a report its person can still see. It lasts
ten minutes, so one copied into a chat or a log is soon worth nothing.
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
from app.mcp_server.auth import person_of
from app.services.credentials import Credential
from app.services.delivery.deliveries import report_pdf_name

PDF_LINK_TTL = timedelta(minutes=10)
# Every sealed link shares one key, so a token made for something else (a signup link) must not pass.
_PURPOSE = "report_pdf"
_GONE = "This download link is wrong or has expired: ask your assistant for the PDF again"

router = APIRouter(prefix="/pdf-links", tags=["reports"])


def pdf_link(report_id: uuid.UUID, credential: Credential) -> str:
    # Every installation serves the API under its panel's origin (Traefik on the hosted service,
    # Caddy on a server of its own); only in development is the API on a port of its own.
    token = seal({"purpose": _PURPOSE, "report": str(report_id), "by": credential.kind, "id": str(credential.id)})
    return f"{settings.FRONTEND_ORIGIN}{settings.API_ROOT_PATH}{router.prefix}/{token}"


@router.get("/{token}")
async def download_by_link(token: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    try:
        claims = unseal(token, PDF_LINK_TTL)
    except ValueError as exc:
        raise ResourceNotFoundException(_GONE) from exc
    # A link sealed before links named the kind of credential ("key") is one of these too.
    if claims.get("purpose") != _PURPOSE or claims.get("by") not in ("api_key", "oauth"):
        raise ResourceNotFoundException(_GONE)
    user = await person_of(db, Credential(claims["by"], uuid.UUID(claims["id"])))
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
