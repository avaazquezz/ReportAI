from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.security import decode_token
from app.models.tenant_user import TenantUser

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> TenantUser:
    if credentials is None:
        raise AuthenticationException("Missing bearer token")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise AuthenticationException(str(exc)) from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationException("Token missing subject")

    result = await db.execute(select(TenantUser).where(TenantUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationException("User not found or inactive")

    return user


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
