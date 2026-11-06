import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.usage import build_usage_summary
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
from app.services import audit, plans
from app.services.notifications.invites import send_invite

router = APIRouter(
    prefix="/admin/tenants", tags=["admin:tenants"], dependencies=[Depends(require_super_admin)]
)
logger = logging.getLogger(__name__)


@router.post("", status_code=201)
async def create_tenant(
    payload: TenantCreateRequest,
    request: Request,
    current_user: TenantUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
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

    # A failed email doesn't roll back the tenant: invite_email_sent=false, retry with /resend-invite.
    invite_sent, _ = await send_invite(db, admin_user)
    await audit.record(
        db, "tenant.created", actor=current_user, tenant_id=tenant.id, target=tenant.id, request=request,
        name=tenant.name, slug=tenant.slug, admin_email=admin_user.email, invite_email_sent=invite_sent,
    )
    return TenantCreateResponse(
        **TenantResponse.model_validate(tenant).model_dump(), invite_email_sent=invite_sent
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
    tenant_id: uuid.UUID,
    payload: TenantUpdateRequest,
    request: Request,
    current_user: TenantUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> TenantResponse:
    repo = BaseRepository(Tenant, db)
    tenant = await repo.get_by_id(tenant_id)
    if tenant is None:
        raise ResourceNotFoundException()
    was_active, old_plan, old_status = tenant.is_active, tenant.plan, tenant.plan_status
    if payload.is_active is not None:
        tenant.is_active = payload.is_active
    cancelled_deletion = tenant.is_active and tenant.deletion_requested_at is not None
    if cancelled_deletion:  # how a company that asked to be deleted changes its mind: via support
        tenant.deletion_requested_at = None
    if payload.plan is not None and payload.plan != tenant.plan:
        plans.start_plan(tenant, payload.plan, payload.plan_status or "active")
    elif payload.plan_status is not None:
        tenant.plan_status = payload.plan_status
    # One event per concern: suspending or reactivating the company, and its plan.
    if tenant.is_active != was_active:
        await audit.record(
            db, "tenant.updated", actor=current_user, tenant_id=tenant.id, target=tenant.id, request=request,
            changes={"is_active": {"from": was_active, "to": tenant.is_active}},
        )
    if cancelled_deletion:
        await audit.record(
            db, "company.deletion_cancelled", actor=current_user, tenant_id=tenant.id, target=tenant.id, request=request
        )
    if (tenant.plan, tenant.plan_status) != (old_plan, old_status):
        await audit.record(
            db, "plan.changed", actor=current_user, tenant_id=tenant.id, target=tenant.id, request=request,
            plan={"from": old_plan, "to": tenant.plan}, plan_status={"from": old_status, "to": tenant.plan_status},
        )
    await db.flush()
    await db.refresh(tenant)
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

    sent, _ = await send_invite(db, admins[0])
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
