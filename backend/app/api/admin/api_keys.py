"""Personal API keys for AI assistants (services/api_keys.py): anyone in a company makes their own
and revokes them; the company's admin sees and revokes everyone's."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_company_user
from app.models.api_key import ApiKey
from app.models.tenant_user import TenantUser
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse
from app.services import api_keys, audit

router = APIRouter(prefix="/api-keys", tags=["admin:api-keys"])


def _response(key: ApiKey, owner_name: str) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        owner_id=key.user_id,
        owner_name=owner_name,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
        expires_at=key.expires_at,
    )


@router.get("")
async def list_api_keys(
    current_user: TenantUser = Depends(require_company_user), db: AsyncSession = Depends(get_db, scope="function")
) -> list[ApiKeyResponse]:
    return [_response(key, owner) for key, owner in await api_keys.visible_keys(db, current_user)]


@router.post("", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    current_user: TenantUser = Depends(require_company_user),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> ApiKeyCreated:
    new = await api_keys.create(db, current_user, body.name.strip() or "API key", body.expires_in_days)
    await audit.record(
        db, "api_key.created", actor=current_user, target=new.key.id, request=request,
        name=new.key.name, prefix=new.key.prefix, expires_in_days=body.expires_in_days,
    )
    await db.commit()
    await db.refresh(new.key)
    return ApiKeyCreated(**_response(new.key, current_user.full_name).model_dump(), secret=new.secret)


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    current_user: TenantUser = Depends(require_company_user),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> Response:
    key = await api_keys.revocable_key(db, current_user, key_id)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await audit.record(db, "api_key.revoked", actor=current_user, target=key.id, request=request, prefix=key.prefix)
        await db.commit()
    return Response(status_code=204)
