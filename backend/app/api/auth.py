import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import TECHNICIAN, can_sign_in, get_current_user, is_demo_user
from app.core.exceptions import (
    AuthenticationException,
    RateLimitException,
    ResourceNotFoundException,
    ValidationException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.used_refresh_token import UsedRefreshToken
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MagicLinkRequest,
    MagicSignInRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services import audit
from app.services.branding import Branding
from app.services.i18n import t
from app.services.notifications.email import send_plain_email
from app.services.notifications.invites import send_magic_link
from app.services.notifications.tokens import (
    MAGIC,
    consume_magic_code,
    consume_reset_token,
    invalidate_sign_ins,
    issue_reset_token,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_FORGOT_PASSWORD_MESSAGE = "If that email exists, we've sent password reset instructions."


def tokens_for(user: TenantUser) -> TokenResponse:
    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "ver": user.token_version,
    }
    days = settings.TECHNICIAN_REFRESH_DAYS if user.role == TECHNICIAN else settings.REFRESH_TOKEN_EXPIRE_DAYS
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token({"sub": str(user.id), "ver": user.token_version}, days),
    )


async def _use_refresh_token(db: AsyncSession, token: str) -> dict[str, Any] | None:
    """Marks a refresh token as spent and returns its claims; None when it is invalid, expired,
    not a refresh token, or was already spent (atomic: two tabs refreshing at once get one winner)."""
    try:
        claims = decode_token(token)
    except ValueError:
        return None
    if claims.get("type") != "refresh" or not claims.get("jti") or not claims.get("sub"):
        return None
    spent = await db.execute(
        pg_insert(UsedRefreshToken)
        .values(jti=claims["jti"], expires_at=datetime.fromtimestamp(claims["exp"], UTC))
        .on_conflict_do_nothing()
        .returning(UsedRefreshToken.jti)
    )
    return claims if spent.scalar_one_or_none() else None


@router.post("/auth/login")
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    email_key, ip_key = payload.email.lower(), audit.client_ip(request)
    await rate_limit.login_by_email.check(db, email_key)
    await rate_limit.login_by_ip.check(db, ip_key)

    result = await db.execute(select(TenantUser).where(TenantUser.email == payload.email))
    user = result.scalar_one_or_none()

    # A technician signs in with an emailed link, never a password (a panel user moved to the
    # technician role may still hold one).
    if (
        user is None
        or user.role == TECHNICIAN
        or not verify_password(payload.password, user.hashed_password)
        or not await can_sign_in(db, user)
    ):
        # Before the attempt is counted: that commit is what keeps the event through the rollback.
        await audit.record(
            db, "auth.login_failed", tenant_id=user.tenant_id if user else None, target=user.id if user else None,
            request=request, email=payload.email[:320],  # unvalidated input: bounded before it is stored
        )
        await rate_limit.login_by_email.record(db, email_key)
        await rate_limit.login_by_ip.record(db, ip_key)
        raise AuthenticationException("Incorrect email or password")
    await rate_limit.login_by_email.reset(db, email_key)
    await audit.record(db, "auth.login_succeeded", actor=user, request=request)
    return tokens_for(user)


@router.post("/auth/demo-login")
async def demo_login(db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """One-click access to the public demo tenant. 404 unless DEMO_USER_EMAIL is
    configured — keeps the endpoint inert outside the demo deployment."""
    if not settings.DEMO_USER_EMAIL:
        raise ResourceNotFoundException()
    result = await db.execute(
        select(TenantUser).where(TenantUser.email == settings.DEMO_USER_EMAIL)
    )
    user = result.scalar_one_or_none()
    if user is None or not await can_sign_in(db, user):
        raise ResourceNotFoundException()
    return tokens_for(user)


@router.post("/auth/refresh")
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """A new pair for an unspent refresh token: the session outlives the one-hour access token
    without asking for the password again, and the old refresh token stops working."""
    claims = await _use_refresh_token(db, payload.refresh_token)
    user = await db.get(TenantUser, uuid.UUID(claims["sub"])) if claims else None
    # A token issued before the password was reset (or the account changed) ends with it.
    if user is None or claims is None or claims.get("ver", 0) != user.token_version or not await can_sign_in(db, user):
        raise AuthenticationException("Session expired, please sign in again")
    return tokens_for(user)


@router.post("/auth/logout")
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    """Spends the refresh token, so signing out also ends the session on the server side."""
    await _use_refresh_token(db, payload.refresh_token)
    return MessageResponse(message="Signed out.")


@router.get("/auth/me")
async def me(current_user: TenantUser = Depends(get_current_user)) -> UserResponse:
    response = UserResponse.model_validate(current_user)
    response.is_demo = is_demo_user(current_user)
    return response


@router.patch("/auth/me")
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    current_user: TenantUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if payload.full_name != current_user.full_name:
        await audit.record(
            db, "auth.profile_updated", actor=current_user, target=current_user.id, request=request,
            changes={"full_name": {"from": current_user.full_name, "to": payload.full_name}},
        )
    current_user.full_name = payload.full_name
    await db.flush()
    return await me(current_user)


@router.post("/auth/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: TenantUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """A new password signs the account out everywhere else; this session gets fresh tokens."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise ValidationException("The current password is not right")
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.token_version += 1
    await audit.record(db, "auth.password_changed", actor=current_user, target=current_user.id, request=request)
    await db.flush()
    return tokens_for(current_user)


@router.post("/auth/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Always returns the same message regardless of whether the email exists — the
    response, and any email-delivery failure, must never let a caller distinguish a
    known account from an unknown one."""
    email_key, ip_key = payload.email.lower(), audit.client_ip(request)
    await rate_limit.forgot_by_email.check(db, email_key)
    await rate_limit.forgot_by_ip.check(db, ip_key)
    await rate_limit.forgot_by_email.record(db, email_key)
    await rate_limit.forgot_by_ip.record(db, ip_key)
    result = await db.execute(select(TenantUser).where(TenantUser.email == payload.email))
    user = result.scalar_one_or_none()
    if user is not None and user.role == TECHNICIAN and await can_sign_in(db, user):
        sent, _ = await send_magic_link(db, user)  # no password to reset: a way in instead
        if sent:
            await audit.record(db, "auth.magic_link_requested", tenant_id=user.tenant_id, target=user.id, request=request)
    elif user is not None and await can_sign_in(db, user):
        token = await issue_reset_token(db, user.id)
        reset_link = f"{settings.FRONTEND_ORIGIN}/reset-password?token={token}"
        tenant = await db.get(Tenant, user.tenant_id) if user.tenant_id else None
        language = tenant.language if tenant else None
        try:
            await send_plain_email(
                to=[user.email],
                subject=t(language, "reset_subject"),
                body=t(language, "reset_body", link=reset_link),
                branding=Branding.of(tenant) if tenant else None,
            )
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
        else:
            # Whoever asked is not signed in: the account it concerns is the target, not the actor.
            await audit.record(
                db, "auth.password_reset_requested", tenant_id=user.tenant_id, target=user.id, request=request,
                email=user.email,
            )
    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/auth/reset-password")
async def reset_password(
    payload: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    try:
        user = await consume_reset_token(db, payload.token)
    except ValueError as exc:
        raise ValidationException(str(exc)) from exc

    user.hashed_password = hash_password(payload.new_password)
    # Whoever knew the old password may still hold a session: it ends here.
    user.token_version += 1
    # The link reached the account's inbox: whoever used it acted as the account.
    await audit.record(db, "auth.password_reset", actor=user, target=user.id, request=request)
    await db.flush()
    return MessageResponse(message="Password updated successfully.")


_MAGIC_LINK_MESSAGE = "If that email belongs to a technician, we've sent them a sign-in link and code."


@router.post("/auth/magic-link")
async def request_magic_link(
    payload: MagicLinkRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """A technician asks for a sign-in link. The same answer whoever asks, so the endpoint never
    says whether an address has an account (or a technician's)."""
    email_key, ip_key = payload.email.lower(), audit.client_ip(request)
    await rate_limit.magic_link_by_email.check(db, email_key)
    await rate_limit.magic_link_by_ip.check(db, ip_key)
    await rate_limit.magic_link_by_email.record(db, email_key)
    await rate_limit.magic_link_by_ip.record(db, ip_key)
    user = await db.scalar(select(TenantUser).where(TenantUser.email == payload.email))
    if user is not None and user.role == TECHNICIAN and await can_sign_in(db, user):
        sent, _ = await send_magic_link(db, user)
        if sent:
            await audit.record(db, "auth.magic_link_requested", tenant_id=user.tenant_id, target=user.id, request=request)
    return MessageResponse(message=_MAGIC_LINK_MESSAGE)


@router.post("/auth/magic")
async def magic_sign_in(
    payload: MagicSignInRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Spends an emailed sign-in (the link's token, or its code typed in the installed app) for a
    session. Every refusal reads the same."""
    refused = AuthenticationException("That sign-in link or code is wrong or has expired. Ask for a new one.")
    if payload.token:
        try:
            user: TenantUser | None = await consume_reset_token(db, payload.token, purpose=MAGIC)
        except ValueError:
            raise refused from None
    elif payload.email is None or payload.code is None:  # the schema already requires both
        raise refused
    else:
        email_key = payload.email.lower()
        await rate_limit.magic_code_by_email.check(db, email_key)
        user = await db.scalar(select(TenantUser).where(TenantUser.email == payload.email))
        if user is None or not await consume_magic_code(db, user.id, payload.code):
            await rate_limit.magic_code_by_email.record(db, email_key)
            try:
                await rate_limit.magic_code_by_email.check(db, email_key)
            except RateLimitException:
                if user is not None:  # the code out there can't be guessed any further
                    await invalidate_sign_ins(db, user.id)
                    await db.commit()
                raise
            raise refused
    if user is None or user.role != TECHNICIAN or not await can_sign_in(db, user):
        raise refused
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await audit.record(db, "auth.magic_sign_in", actor=user, target=user.id, request=request)
    await db.flush()
    return tokens_for(user)
