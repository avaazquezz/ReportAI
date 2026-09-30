import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, is_demo_user
from app.core.exceptions import (
    AuthenticationException,
    ResourceNotFoundException,
    ValidationException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.tenant_user import TenantUser
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.notifications.email import send_plain_email
from app.services.notifications.tokens import consume_reset_token, issue_reset_token

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_FORGOT_PASSWORD_MESSAGE = "If that email exists, we've sent password reset instructions."


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/auth/login")
async def login(
    payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    email_key, ip_key = payload.email.lower(), _client_ip(request)
    rate_limit.login_by_email.check(email_key)
    rate_limit.login_by_ip.check(ip_key)

    result = await db.execute(select(TenantUser).where(TenantUser.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        rate_limit.login_by_email.record(email_key)
        rate_limit.login_by_ip.record(ip_key)
        raise AuthenticationException("Incorrect email or password")
    rate_limit.login_by_email.reset(email_key)

    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )


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
    if user is None or not user.is_active:
        raise ResourceNotFoundException()

    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }
    return TokenResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )


@router.get("/auth/me")
async def me(current_user: TenantUser = Depends(get_current_user)) -> UserResponse:
    response = UserResponse.model_validate(current_user)
    response.is_demo = is_demo_user(current_user)
    return response


@router.post("/auth/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Always returns the same message regardless of whether the email exists — the
    response, and any email-delivery failure, must never let a caller distinguish a
    known account from an unknown one."""
    email_key, ip_key = payload.email.lower(), _client_ip(request)
    rate_limit.forgot_by_email.check(email_key)
    rate_limit.forgot_by_ip.check(ip_key)
    rate_limit.forgot_by_email.record(email_key)
    rate_limit.forgot_by_ip.record(ip_key)
    result = await db.execute(select(TenantUser).where(TenantUser.email == payload.email))
    user = result.scalar_one_or_none()
    if user is not None and user.is_active:
        token = await issue_reset_token(db, user.id)
        reset_link = f"{settings.FRONTEND_ORIGIN}/reset-password?token={token}"
        try:
            await send_plain_email(
                to=[user.email],
                subject="Reset your ReportAI password",
                body=f"Use this link to set a new password (expires in 1 hour):\n\n{reset_link}",
            )
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
    return MessageResponse(message=_FORGOT_PASSWORD_MESSAGE)


@router.post("/auth/reset-password")
async def reset_password(
    payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    try:
        user = await consume_reset_token(db, payload.token)
    except ValueError as exc:
        raise ValidationException(str(exc)) from exc

    user.hashed_password = hash_password(payload.new_password)
    await db.flush()
    return MessageResponse(message="Password updated successfully.")
