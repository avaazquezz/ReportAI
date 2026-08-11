import logging
import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.usage import build_usage_summary
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_super_admin
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantCreateResponse,
    TenantResponse,
    TenantUpdateRequest,
)
from app.schemas.usage import UsageSummaryResponse
from app.services.notifications.email import send_plain_email
from app.services.notifications.tokens import issue_reset_token

router = APIRouter(
    prefix="/admin/tenants", tags=["admin:tenants"], dependencies=[Depends(require_super_admin)]
)
logger = logging.getLogger(__name__)


async def _send_invite(user: TenantUser, db: AsyncSession) -> bool:
    """Issue a reset token and email it as a "set your password" link — the same
    mechanism as forgot-password, so a super-admin never sees/sets a tenant admin's
    real password. Returns whether the email actually sent; a failure here doesn't
    roll back tenant/user creation, it just leaves invite_email_sent=false for the
    caller to retry via /resend-invite."""
    token = await issue_reset_token(db, user.id)
    link = f"{settings.FRONTEND_ORIGIN}/reset-password?token={token}"
    try:
        await send_plain_email(
            to=[user.email],
            subject="You've been invited to ReportAI",
            body=f"An account was created for you. Set your password here (expires in 1 hour):\n\n{link}",
        )
        return True
    except Exception:
        logger.exception("Failed to send tenant invite email to %s", user.email)
        return False


@router.post("", status_code=201)
async def create_tenant(
    payload: TenantCreateRequest, db: AsyncSession = Depends(get_db)
) -> TenantCreateResponse:
    tenant_repo = BaseRepository(Tenant, db)
    try:
        tenant = await tenant_repo.create(name=payload.name, slug=payload.slug, is_active=True)
    except IntegrityError as exc:
        raise ConflictException(f"Tenant slug {payload.slug!r} already exists") from exc

    user_repo = BaseRepository(TenantUser, db)
    # Random, never revealed, unusable-by-construction placeholder — the admin sets
    # their real password via the invite link, no plaintext temp password ever exists.
    admin_user = await user_repo.create(
        tenant_id=tenant.id,
        email=payload.admin_email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        full_name=payload.admin_full_name,
        role="tenant_admin",
        is_active=True,
    )

    invite_sent = await _send_invite(admin_user, db)
    return TenantCreateResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
        invite_email_sent=invite_sent,
    )


@router.get("")
async def list_tenants(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> PaginatedResponse[TenantResponse]:
    repo = BaseRepository(Tenant, db)
    items = await repo.list(skip=skip, limit=limit)
    total = await repo.count()
    return PaginatedResponse(
        items=[TenantResponse.model_validate(t) for t in items], total=total, skip=skip, limit=limit
    )


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> TenantResponse:
    repo = BaseRepository(Tenant, db)
    tenant = await repo.get_by_id(tenant_id)
    if tenant is None:
        raise ResourceNotFoundException()
    return TenantResponse.model_validate(tenant)


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID, payload: TenantUpdateRequest, db: AsyncSession = Depends(get_db)
) -> TenantResponse:
    repo = BaseRepository(Tenant, db)
    tenant = await repo.get_by_id(tenant_id)
    if tenant is None:
        raise ResourceNotFoundException()
    tenant = await repo.update(tenant, is_active=payload.is_active)
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_id}/resend-invite")
async def resend_invite(tenant_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    tenant_repo = BaseRepository(Tenant, db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise ResourceNotFoundException()

    user_repo = BaseRepository(TenantUser, db)
    admins = await user_repo.list(filters={"tenant_id": tenant.id, "role": "tenant_admin"}, limit=1)
    if not admins:
        raise ResourceNotFoundException("This tenant has no admin user to invite")

    sent = await _send_invite(admins[0], db)
    return MessageResponse(message="Invite sent" if sent else "Failed to send invite email")


@router.get("/{tenant_id}/usage/summary")
async def get_tenant_usage_summary(
    tenant_id: uuid.UUID, days: int = 30, db: AsyncSession = Depends(get_db)
) -> UsageSummaryResponse:
    tenant_repo = BaseRepository(Tenant, db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if tenant is None:
        raise ResourceNotFoundException()
    return await build_usage_summary(db, tenant_id=tenant_id, days=days)
