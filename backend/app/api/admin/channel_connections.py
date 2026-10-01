import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.exceptions import ConflictException, ResourceNotFoundException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.channel_connection import ChannelConnection
from app.models.sender_invite import SenderInvite
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository
from app.schemas.channel_connection import (
    ChannelConnectionCreateRequest,
    ChannelConnectionResponse,
    ChannelConnectionUpdateRequest,
    SenderInviteCreatedResponse,
    SenderInviteCreateRequest,
    SenderInviteResponse,
    routing_key_for,
)
from app.schemas.common import PaginatedResponse
from app.services.channels.telegram_webhook import register_telegram_webhook, verify_telegram_bot
from app.services.sender_invites import create_invite, sender_labels, telegram_link

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
        credentials["bot_username"] = await verify_telegram_bot(credentials["bot_token"])
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
    labels = await sender_labels(db, [connection.id])
    return ChannelConnectionResponse.from_model(connection, labels.get(connection.id))


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
    labels = await sender_labels(db, [c.id for c in items])
    return PaginatedResponse(
        items=[ChannelConnectionResponse.from_model(c, labels.get(c.id)) for c in items],
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
    labels = await sender_labels(db, [connection.id])
    return ChannelConnectionResponse.from_model(connection, labels.get(connection.id))


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
        if connection.channel_type == "telegram" and "bot_token" in payload.credentials:
            merged_credentials["bot_username"] = await verify_telegram_bot(payload.credentials["bot_token"])

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
    labels = await sender_labels(db, [connection.id])
    return ChannelConnectionResponse.from_model(connection, labels.get(connection.id))


@router.post("/{connection_id}/invites", status_code=201)
async def create_sender_invite(
    connection_id: uuid.UUID,
    payload: SenderInviteCreateRequest,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> SenderInviteCreatedResponse:
    """An invitation for one person: a link to open (Telegram) or a code to send to the channel."""
    tenant_id = require_tenant_id(current_user)
    connection = await get_scoped_or_404(BaseRepository(ChannelConnection, db), connection_id, tenant_id=tenant_id)
    if connection.channel_type == "telegram" and not connection.credentials.get("bot_username"):
        # Saved before bots were looked up: the link needs the bot's @username.
        username = await verify_telegram_bot(connection.credentials["bot_token"])
        connection.credentials = {**connection.credentials, "bot_username": username}
    invite, code = await create_invite(db, connection, payload.label, current_user.id)
    return SenderInviteCreatedResponse(
        **SenderInviteResponse.model_validate(invite).model_dump(),
        code=code,
        link=telegram_link(connection, code) if connection.channel_type == "telegram" else None,
    )


@router.get("/{connection_id}/invites")
async def list_sender_invites(
    connection_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SenderInviteResponse]:
    tenant_id = require_tenant_id(current_user)
    await get_scoped_or_404(BaseRepository(ChannelConnection, db), connection_id, tenant_id=tenant_id)
    invites = await db.scalars(
        select(SenderInvite).where(SenderInvite.connection_id == connection_id).order_by(SenderInvite.created_at.desc())
    )
    return [SenderInviteResponse.model_validate(i) for i in invites]


@router.delete("/{connection_id}/invites/{invite_id}", status_code=204)
async def revoke_sender_invite(
    connection_id: uuid.UUID,
    invite_id: uuid.UUID,
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """An unused invitation stops working. (A used one is history: remove the sender instead.)"""
    tenant_id = require_tenant_id(current_user)
    await get_scoped_or_404(BaseRepository(ChannelConnection, db), connection_id, tenant_id=tenant_id)
    invite = await db.get(SenderInvite, invite_id)
    if invite is None or invite.connection_id != connection_id:
        raise ResourceNotFoundException()
    if invite.used_at is not None:
        raise ConflictException("This invitation was already used")
    await db.delete(invite)
