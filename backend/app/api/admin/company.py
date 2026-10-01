"""The company itself: its name, the language its people are answered in, its clock, and its
look (logo and colour) on the emails and documents ReportAI sends for it."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin, require_tenant_member
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import require_tenant_id
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.company import CompanyResponse, CompanyUpdateRequest
from app.services.branding import InvalidLogoError, store_logo

router = APIRouter(prefix="/company", tags=["admin:company"])

_MAX_LOGO_BYTES = 5 * 1024 * 1024


async def _tenant(db: AsyncSession, user: TenantUser) -> Tenant:
    tenant = await db.get(Tenant, require_tenant_id(user))
    assert tenant is not None
    return tenant


def _response(tenant: Tenant) -> CompanyResponse:
    return CompanyResponse(
        name=tenant.name,
        language=tenant.language,
        timezone=tenant.timezone,
        brand_color=tenant.brand_color,
        has_logo=bool(tenant.logo_path and Path(tenant.logo_path).exists()),
    )


def _forget(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


@router.get("")
async def get_company(
    current_user: TenantUser = Depends(require_tenant_member), db: AsyncSession = Depends(get_db)
) -> CompanyResponse:
    return _response(await _tenant(db, current_user))


@router.patch("")
async def update_company(
    payload: CompanyUpdateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    tenant = await _tenant(db, current_user)
    tenant.name, tenant.language, tenant.timezone = payload.name, payload.language, payload.timezone
    tenant.brand_color = payload.brand_color.upper() if payload.brand_color else None
    await db.flush()
    return _response(tenant)


@router.put("/logo")
async def upload_logo(
    file: UploadFile,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    raw = await file.read(_MAX_LOGO_BYTES + 1)
    if len(raw) > _MAX_LOGO_BYTES:
        raise ValidationException("The logo must be under 5 MB")
    tenant = await _tenant(db, current_user)
    try:
        path = await asyncio.to_thread(store_logo, tenant.id, raw)
    except InvalidLogoError as exc:
        raise ValidationException(str(exc)) from exc
    previous, tenant.logo_path = tenant.logo_path, path
    await db.flush()
    _forget(previous)
    return _response(tenant)


@router.delete("/logo")
async def delete_logo(
    current_user: TenantUser = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db)
) -> CompanyResponse:
    tenant = await _tenant(db, current_user)
    previous, tenant.logo_path = tenant.logo_path, None
    await db.flush()
    _forget(previous)
    return _response(tenant)


@router.get("/logo")
async def get_logo(
    current_user: TenantUser = Depends(require_tenant_member), db: AsyncSession = Depends(get_db)
) -> FileResponse:
    tenant = await _tenant(db, current_user)
    if not tenant.logo_path or not Path(tenant.logo_path).exists():
        raise ResourceNotFoundException("This company has no logo")
    return FileResponse(tenant.logo_path, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
