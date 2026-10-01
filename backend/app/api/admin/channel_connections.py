import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ConflictException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.channel_connection import ChannelConnection
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.channel_connection import (
    ChannelConnectionCreateRequest,
    ChannelConnectionResponse,
    ChannelConnectionUpdateRequest,
    routing_key_for,
)
from app.schemas.common import PaginatedResponse
from app.services.channels.telegram_webhook import register_telegram_webhook

router = APIRouter(prefix="/channels", tags=["admin:channels"])

# Two connections answering the same WhatsApp number or inbound address could not be told apart.
_ROUTING_TAKEN = "Another connection already uses this phone number id or inbound address"


@router.post("", status_code=201)
async def create_channel_connection(
    payload: ChannelConnectionCreateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ChannelConnectionResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(ChannelConnection, db)
    credentials = dict(payload.credentials)
    connection_id = uuid.uuid4()
    if payload.channel_type == "telegram":
        # Echoed back by Telegram on every webhook update and verified there.
        credentials.setdefault("secret_token", secrets.token_urlsafe(32))
        await register_telegram_webhook(connection_id, credentials)
    try:
        connection = await repo.create(
            id=connection_id,
            tenant_id=tenant_id,
            channel_type=payload.channel_type,
            display_name=payload.display_name,
            credentials=credentials,
            routing_key=routing_key_for(payload.channel_type, credentials),
            allowed_senders=payload.allowed_senders,
            is_active=True,
        )
    except IntegrityError as exc:
        raise ConflictException(_ROUTING_TAKEN) from exc
    return ChannelConnectionResponse.from_model(connection)


@router.get("")
async def list_channel_connections(
    skip: int = 0,
    limit: int = 100,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ChannelConnectionResponse]:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(ChannelConnection, db)
    filters = {"tenant_id": tenant_id}
    items = await repo.list(skip=skip, limit=limit, filters=filters)
    total = await repo.count(filters=filters)
    return PaginatedResponse(
        items=[ChannelConnectionResponse.from_model(c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{connection_id}")
async def get_channel_connection(
    connection_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ChannelConnectionResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(ChannelConnection, db)
    connection = await get_scoped_or_404(repo, connection_id, tenant_id=tenant_id)
    return ChannelConnectionResponse.from_model(connection)


@router.patch("/{connection_id}")
async def update_channel_connection(
    connection_id: uuid.UUID,
    payload: ChannelConnectionUpdateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ChannelConnectionResponse:
    tenant_id = require_tenant_id(current_user)
    repo = BaseRepository(ChannelConnection, db)
    connection = await get_scoped_or_404(repo, connection_id, tenant_id=tenant_id)

    merged_credentials = dict(connection.credentials)
    if payload.credentials:
        merged_credentials.update(payload.credentials)

    # Only when something Telegram cares about changed (a new token, or switching back on),
    # so editing allowed senders doesn't depend on Telegram being reachable.
    if connection.channel_type == "telegram" and (
        payload.credentials or (payload.is_active and not connection.is_active)
    ):
        merged_credentials.setdefault("secret_token", secrets.token_urlsafe(32))
        await register_telegram_webhook(connection.id, merged_credentials)

    try:
        connection = await repo.update(
            connection,
            display_name=payload.display_name,
            credentials=merged_credentials,
            routing_key=routing_key_for(connection.channel_type, merged_credentials),
            allowed_senders=payload.allowed_senders,
            is_active=payload.is_active,
        )
    except IntegrityError as exc:
        raise ConflictException(_ROUTING_TAKEN) from exc
    return ChannelConnectionResponse.from_model(connection)
