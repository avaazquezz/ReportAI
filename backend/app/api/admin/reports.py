import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ResourceNotFoundException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.report import Report
from app.models.tenant_user import TenantUser
from app.repositories.report_repository import ReportRepository
from app.schemas.common import PaginatedResponse
from app.schemas.report import ReportResponse

router = APIRouter(prefix="/reports", tags=["admin:reports"])


def _to_response(report: Report, document_type_name: str | None) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        tenant_id=report.tenant_id,
        document_type_id=report.document_type_id,
        document_type_name=document_type_name,
        status=report.status,
        requester_channel=report.requester_channel,
        requester_identifier=report.requester_identifier,
        error_detail=report.error_detail,
        download_url=f"/reports/{report.id}/download" if report.file_path else None,
        created_at=report.created_at,
        completed_at=report.completed_at,
    )


@router.get("")
async def list_reports(
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ReportResponse]:
    tenant_id = require_tenant_id(current_user)
    repo = ReportRepository(db)
    rows = await repo.list_with_document_type_name(
        tenant_id=tenant_id, skip=skip, limit=limit, status=status
    )
    total = await repo.count_scoped(tenant_id=tenant_id, status=status)
    return PaginatedResponse(
        items=[_to_response(report, name) for report, name in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    tenant_id = require_tenant_id(current_user)
    repo = ReportRepository(db)
    row = await repo.get_with_document_type_name(report_id)
    if row is None or row[0].tenant_id != tenant_id:
        raise ResourceNotFoundException()
    report, document_type_name = row
    return _to_response(report, document_type_name)


@router.get("/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    tenant_id = require_tenant_id(current_user)
    repo = ReportRepository(db)
    report = await get_scoped_or_404(repo, report_id, tenant_id=tenant_id)
    if not report.file_path:
        raise ResourceNotFoundException("No file available for this report")
    return FileResponse(report.file_path, filename=Path(report.file_path).name)
