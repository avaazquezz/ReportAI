import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.models.tenant_user import TenantUser

_TOKEN_TTL = timedelta(hours=1)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def _invalidate_outstanding_tokens(db: AsyncSession, tenant_user_id: uuid.UUID) -> None:
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.tenant_user_id == tenant_user_id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )


async def issue_reset_token(db: AsyncSession, tenant_user_id: uuid.UUID) -> str:
    """Mint a single-use reset/invite token. Returns the raw token (goes in the emailed
    link, never stored) — only its hash is persisted. Invalidates any still-outstanding
    tokens for this user first, so re-requesting a reset kills older, possibly-leaked links."""
    await _invalidate_outstanding_tokens(db, tenant_user_id)
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            tenant_user_id=tenant_user_id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(UTC) + _TOKEN_TTL,
        )
    )
    await db.flush()
    return raw_token


async def consume_reset_token(db: AsyncSession, raw_token: str) -> TenantUser:
    """Validate + burn a reset token, returning the user it belongs to. Raises ValueError
    (never leaking *why*) on an unknown, expired, or already-used token."""
    token_result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(raw_token))
    )
    token = token_result.scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at < now:
        raise ValueError("Invalid or expired token")

    user_result = await db.execute(select(TenantUser).where(TenantUser.id == token.tenant_user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError("Invalid or expired token")

    # Burns this token and any other outstanding tokens for the same user in one statement.
    await _invalidate_outstanding_tokens(db, token.tenant_user_id)
    await db.flush()
    return user
