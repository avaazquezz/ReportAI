from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AuthenticationException
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models.tenant_user import TenantUser
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    result = await db.execute(select(TenantUser).where(TenantUser.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise AuthenticationException("Email o contraseña incorrectos")

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
    return UserResponse.model_validate(current_user)
