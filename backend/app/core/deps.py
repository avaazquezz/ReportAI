from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.security import decode_token
from app.models.tenant_user import TenantUser

bearer_scheme = HTTPBearer(auto_error=False)

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_demo_user(user: TenantUser) -> bool:
    return bool(settings.DEMO_USER_EMAIL) and user.email == settings.DEMO_USER_EMAIL


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> TenantUser:
    if credentials is None:
        raise AuthenticationException("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise AuthenticationException(str(exc)) from exc

    if payload.get("type") != "access":
        raise AuthenticationException("Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationException("Token missing subject")

    result = await db.execute(select(TenantUser).where(TenantUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationException("User not found or inactive")
    if payload.get("ver", 0) != user.token_version:
        raise AuthenticationException("Session ended, please sign in again")

    # One guard at the single auth entry point: the public demo account can look at
    # everything and change nothing (a writable demo tenant would let any visitor
    # point notification_emails at arbitrary addresses — an SMTP spam vector).
    if is_demo_user(user) and request.method not in _READ_METHODS:
        raise AuthorizationException("Demo mode is read-only")

    return user


# What a company's people can be: its admin runs everything; an approver reviews, corrects and
# sends reports; a viewer only reads them.
TENANT_ROLES = ("tenant_admin", "approver", "viewer")


async def require_tenant_member(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    if current_user.role not in {*TENANT_ROLES, "super_admin"}:
        raise AuthorizationException("Not a member of a company")
    return current_user


async def require_approver(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    if current_user.role not in {"tenant_admin", "approver", "super_admin"}:
        raise AuthorizationException("Approver role required")
    return current_user


async def require_tenant_admin(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    if current_user.role not in {"tenant_admin", "super_admin"}:
        raise AuthorizationException("Tenant admin role required")
    return current_user


async def require_super_admin(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    if current_user.role != "super_admin":
        raise AuthorizationException("Super admin role required")
    return current_user


async def require_instance_admin(
    current_user: TenantUser = Depends(get_current_user),
) -> TenantUser:
    """Whoever runs this installation (its AI provider, mail server, updates): the company's
    admin when it serves one company, the super admin when it hosts several."""
    expected = "tenant_admin" if settings.SINGLE_TENANT else "super_admin"
    if current_user.role != expected:
        raise AuthorizationException("Only the administrator of this installation can do this")
    return current_user
