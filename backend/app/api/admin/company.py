"""The company itself: its name, the language its people are answered in, its clock, and its
look (logo and colour) on the emails and documents ReportAI sends for it."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_company_user, require_tenant_admin, require_tenant_member
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import require_tenant_id
from app.core.security import verify_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.schemas.company import (
    CompanyDeletionRequest,
    CompanyDeletionResponse,
    CompanyResponse,
    CompanyUpdateRequest,
    PlanUsageResponse,
)
from app.services import audit, data_lifecycle, plans
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
        reply_to_email=tenant.reply_to_email,
        has_logo=bool(tenant.logo_path and Path(tenant.logo_path).exists()),
    )


def _settings(tenant: Tenant) -> dict[str, str | None]:
    return {
        "name": tenant.name, "language": tenant.language, "timezone": tenant.timezone,
        "brand_color": tenant.brand_color, "reply_to_email": tenant.reply_to_email,
    }


def _forget(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


@router.get("")
async def get_company(
    current_user: TenantUser = Depends(require_company_user), db: AsyncSession = Depends(get_db)
) -> CompanyResponse:
    return _response(await _tenant(db, current_user))


@router.get("/plan")
async def get_plan(
    current_user: TenantUser = Depends(require_tenant_member), db: AsyncSession = Depends(get_db)
) -> PlanUsageResponse:
    tenant = await _tenant(db, current_user)
    return PlanUsageResponse(
        plan=tenant.plan,
        status=tenant.plan_status,
        period_start=tenant.plan_period_start,
        period_end=tenant.plan_period_end,
        reports_used=await plans.reports_this_period(db, tenant),
        reports_limit=None if settings.SINGLE_TENANT else plans.plan_of(tenant).monthly_reports,
    )


@router.delete("", status_code=202)
async def delete_company(
    payload: CompanyDeletionRequest,
    request: Request,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyDeletionResponse:
    """Blocks the company at once (nobody in it can sign in or send anything) and purges all its
    data when the grace period ends; until then, reactivating it (support) cancels the deletion.
    An installation's only company is deleted by uninstalling, not from here."""
    if settings.SINGLE_TENANT:
        raise ResourceNotFoundException()
    tenant = await _tenant(db, current_user)
    # The password stands between a stolen session and the company's data: guessing it here
    # spends the same attempts as the login form.
    email_key = current_user.email.lower()
    await rate_limit.login_by_email.check(db, email_key)
    if not verify_password(payload.password, current_user.hashed_password):
        await rate_limit.login_by_email.record(db, email_key)
        raise ValidationException("That password is wrong")
    if payload.company_name.strip() != tenant.name.strip():
        raise ValidationException("Type the company's name exactly as it appears to confirm")
    tenant.is_active = False
    tenant.deletion_requested_at = datetime.now(UTC)
    await audit.record(db, "company.deletion_requested", actor=current_user, target=tenant.id, request=request)
    await db.flush()
    return CompanyDeletionResponse(purge_after=tenant.deletion_requested_at + data_lifecycle.DELETION_GRACE)


@router.patch("")
async def update_company(
    payload: CompanyUpdateRequest,
    request: Request,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    tenant = await _tenant(db, current_user)
    before = _settings(tenant)
    tenant.name, tenant.language, tenant.timezone = payload.name, payload.language, payload.timezone
    tenant.brand_color = payload.brand_color.upper() if payload.brand_color else None
    tenant.reply_to_email = payload.reply_to_email
    if fields := audit.changed_fields(before, _settings(tenant)):
        await audit.record(db, "company.updated", actor=current_user, target=tenant.id, request=request, fields=fields)
    await db.flush()
    return _response(tenant)


@router.put("/logo")
async def upload_logo(
    file: UploadFile,
    request: Request,
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
    await audit.record(db, "company.logo_set", actor=current_user, target=tenant.id, request=request)
    await db.flush()
    _forget(previous)
    return _response(tenant)


@router.delete("/logo")
async def delete_logo(
    request: Request,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    tenant = await _tenant(db, current_user)
    previous, tenant.logo_path = tenant.logo_path, None
    if previous:
        await audit.record(db, "company.logo_removed", actor=current_user, target=tenant.id, request=request)
    await db.flush()
    _forget(previous)
    return _response(tenant)


@router.get("/logo")
async def get_logo(
    current_user: TenantUser = Depends(require_company_user), db: AsyncSession = Depends(get_db)
) -> FileResponse:
    tenant = await _tenant(db, current_user)
    if not tenant.logo_path or not Path(tenant.logo_path).exists():
        raise ResourceNotFoundException("This company has no logo")
    return FileResponse(tenant.logo_path, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
