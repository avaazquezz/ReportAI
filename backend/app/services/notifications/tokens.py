import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken
from app.models.tenant_user import TenantUser
from app.services.sender_invites import hash_typed_code, typed_code

_TOKEN_TTL = timedelta(hours=1)
# An invitation is often read the next day: a password reset is asked for and used at once.
INVITE_TTL = timedelta(days=7)
# A technician asks for a sign-in link standing in front of the site and uses it straight away.
MAGIC_TTL = timedelta(minutes=15)
RESET, MAGIC = "reset", "magic"


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


async def issue_reset_token(
    db: AsyncSession, tenant_user_id: uuid.UUID, ttl: timedelta = _TOKEN_TTL, *, code_hash: str | None = None,
    purpose: str = RESET,
) -> str:
    """Mint a single-use reset/invite token. Returns the raw token (goes in the emailed
    link, never stored) — only its hash is persisted. Invalidates any still-outstanding
    tokens for this user first, so re-requesting a reset kills older, possibly-leaked links."""
    await _invalidate_outstanding_tokens(db, tenant_user_id)
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            tenant_user_id=tenant_user_id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(UTC) + ttl,
            purpose=purpose,
            code_hash=code_hash,
        )
    )
    await db.flush()
    return raw_token


async def issue_magic_link(db: AsyncSession, tenant_user_id: uuid.UUID, ttl: timedelta = MAGIC_TTL) -> tuple[str, str]:
    """A technician's single-use sign-in: the token for the link and the same sign-in as a code
    to type ("ABCD-EFGH"). Only hashes are stored; older links and codes stop working."""
    code_hash, code = typed_code()
    return await issue_reset_token(db, tenant_user_id, ttl, code_hash=code_hash, purpose=MAGIC), code


async def consume_reset_token(db: AsyncSession, raw_token: str, *, purpose: str = RESET) -> TenantUser:
    """Validate + burn a reset token, returning the user it belongs to. Raises ValueError
    (never leaking *why*) on an unknown, expired, already-used token, or one minted for the
    other purpose (a reset link never signs anyone in; a sign-in link never sets a password)."""
    token_result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(raw_token))
    )
    token = token_result.scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at < now or token.purpose != purpose:
        raise ValueError("Invalid or expired token")

    user_result = await db.execute(select(TenantUser).where(TenantUser.id == token.tenant_user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError("Invalid or expired token")

    # Burns this token and any other outstanding tokens for the same user in one statement.
    await _invalidate_outstanding_tokens(db, token.tenant_user_id)
    await db.flush()
    return user


async def consume_magic_code(db: AsyncSession, tenant_user_id: uuid.UUID, code: str) -> bool:
    """Burns the person's outstanding sign-in if `code` is its typed twin. False otherwise."""
    token = await db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.tenant_user_id == tenant_user_id,
            PasswordResetToken.purpose == MAGIC,
            PasswordResetToken.code_hash == hash_typed_code(code),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at >= datetime.now(UTC),
        )
    )
    if token is None:
        return False
    await _invalidate_outstanding_tokens(db, tenant_user_id)
    await db.flush()
    return True


async def invalidate_sign_ins(db: AsyncSession, tenant_user_id: uuid.UUID) -> None:
    """Too many wrong codes: whatever link or code is out there stops working."""
    await _invalidate_outstanding_tokens(db, tenant_user_id)
