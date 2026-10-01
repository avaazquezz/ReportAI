"""Letting a person write to a channel without anyone copying chat ids: the admin creates an
invitation for them in the panel, and the person opens its link (Telegram: t.me/<bot>?start=CODE)
or sends its code to the bot. That adds them to the channel's allowed senders, once."""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_connection import ChannelConnection
from app.models.sender_invite import SenderInvite

INVITE_TTL = timedelta(days=7)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # read off a screen and typed: no 0/O, 1/I/L
_CODE_LENGTH = 8
# Telegram's deep link sends "/start CODE"; elsewhere the message is the code itself.
_CODE_MESSAGE = re.compile(rf"^(?:/start\s+)?([{_ALPHABET}]{{4}}-?[{_ALPHABET}]{{4}})$", re.IGNORECASE)


def _hash(code: str) -> str:
    return hashlib.sha256(code.upper().replace("-", "").encode()).hexdigest()


def code_in(text: str | None) -> str | None:
    """The invitation code a message consists of, if it is one."""
    match = _CODE_MESSAGE.match((text or "").strip())
    return match.group(1) if match else None


def is_start_command(text: str | None) -> bool:
    return (text or "").strip().lower().startswith("/start")


def telegram_link(connection: ChannelConnection, code: str) -> str | None:
    username = connection.credentials.get("bot_username")
    return f"https://t.me/{username}?start={code.replace('-', '')}" if username else None


async def create_invite(
    session: AsyncSession, connection: ChannelConnection, label: str, created_by: uuid.UUID
) -> tuple[SenderInvite, str]:
    """A new invitation and its code (shown once: only its hash is kept)."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    invite = SenderInvite(
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        label=label,
        code_hash=_hash(raw),
        expires_at=datetime.now(UTC) + INVITE_TTL,
        created_by=created_by,
    )
    session.add(invite)
    await session.flush()
    return invite, f"{raw[:4]}-{raw[4:]}"


async def redeem(session: AsyncSession, connection: ChannelConnection, code: str, sender_id: str) -> SenderInvite | None:
    """Spends a valid code of this channel on `sender_id` and lets them in. None when the code is
    unknown, expired, already used, or belongs to another channel."""
    invite: SenderInvite | None = await session.scalar(
        update(SenderInvite)
        .where(
            SenderInvite.code_hash == _hash(code),
            SenderInvite.connection_id == connection.id,
            SenderInvite.used_at.is_(None),
            SenderInvite.expires_at > datetime.now(UTC),
        )
        .values(used_at=datetime.now(UTC), sender_id=sender_id)
        .returning(SenderInvite)
    )
    if invite is None:
        return None
    if sender_id not in connection.allowed_senders:
        connection.allowed_senders = [*connection.allowed_senders, sender_id]
    await session.flush()
    return invite


async def sender_labels(session: AsyncSession, connection_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, str]]:
    """Who each allowed sender is, by the name their invitation was made for."""
    rows = await session.execute(
        select(SenderInvite.connection_id, SenderInvite.sender_id, SenderInvite.label)
        .where(SenderInvite.connection_id.in_(connection_ids), SenderInvite.sender_id.is_not(None))
        .order_by(SenderInvite.used_at)
    )
    labels: dict[uuid.UUID, dict[str, str]] = {}
    for connection_id, sender_id, label in rows:
        if sender_id:
            labels.setdefault(connection_id, {})[sender_id] = label
    return labels
