"""A company's people in the panel: who can sign in, and as what (admin, approver, read-only)."""

import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ConflictException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.core.security import hash_password
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.team import (
    TeamInviteRequest,
    TeamInviteResponse,
    TeamMemberResponse,
    TeamMemberUpdateRequest,
)
from app.services.notifications.invites import send_invite

router = APIRouter(prefix="/team", tags=["admin:team"])


@router.get("")
async def list_team(
    current_user: TenantUser = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db)
) -> list[TeamMemberResponse]:
    tenant_id = require_tenant_id(current_user)
    members = await db.scalars(
        select(TenantUser).where(TenantUser.tenant_id == tenant_id).order_by(TenantUser.created_at)
    )
    return [TeamMemberResponse.model_validate(m) for m in members]


@router.post("", status_code=201)
async def invite_member(
    payload: TeamInviteRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> TeamInviteResponse:
    tenant_id = require_tenant_id(current_user)
    try:
        member = await BaseRepository(TenantUser, db).create(
            tenant_id=tenant_id,
            email=payload.email,
            # Unusable until they choose their own through the invitation link.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name=payload.full_name,
            role=payload.role,
            is_active=True,
        )
    except IntegrityError as exc:
        raise ConflictException(f"{payload.email} already has an account") from exc
    sent, link = await send_invite(db, member)
    return TeamInviteResponse(
        member=TeamMemberResponse.model_validate(member), invite_email_sent=sent, invite_link=None if sent else link
    )


@router.patch("/{member_id}")
async def update_member(
    member_id: uuid.UUID,
    payload: TeamMemberUpdateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberResponse:
    tenant_id = require_tenant_id(current_user)
    member = await get_scoped_or_404(BaseRepository(TenantUser, db), member_id, tenant_id=tenant_id)
    changes_access = (payload.role is not None and payload.role != member.role) or (
        payload.is_active is not None and payload.is_active != member.is_active
    )
    # The admin making the change always remains: nobody can lock the company out of its panel.
    if changes_access and member.id == current_user.id:
        raise ValidationException("You can't change your own role or deactivate yourself; ask another admin")
    if payload.full_name is not None:
        member.full_name = payload.full_name
    if payload.role is not None:
        member.role = payload.role
    if payload.is_active is not None:
        member.is_active = payload.is_active
    if changes_access:
        member.token_version += 1  # their open sessions end with their old access
    await db.flush()
    return TeamMemberResponse.model_validate(member)


@router.post("/{member_id}/invite")
async def resend_invite(
    member_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> TeamInviteResponse:
    tenant_id = require_tenant_id(current_user)
    member = await get_scoped_or_404(BaseRepository(TenantUser, db), member_id, tenant_id=tenant_id)
    if not member.is_active:
        raise ValidationException("Activate this person before inviting them again")
    sent, link = await send_invite(db, member)
    return TeamInviteResponse(
        member=TeamMemberResponse.model_validate(member), invite_email_sent=sent, invite_link=None if sent else link
    )
