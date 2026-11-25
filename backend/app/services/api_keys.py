"""Personal API keys for AI assistants. A company user makes one in the panel and gives it to their
assistant (Claude, through the MCP server in app/mcp_server/): the key acts as that person, with
their role, through the same checks the panel uses, so it never sees or does more than they can.

What a key is worth follows its person: it stops working the moment they may not sign in (deactivated,
company suspended or deleted) and works again if they are let back in. Revoking a key ends it for
good, and so does its expiry date, if it was made with one (30, 90 or 365 days; none never expires).
Only a hash of the secret is kept; the secret is shown once, when it is made.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import can_sign_in, is_demo_user
from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.scoping import get_scoped_or_404, require_tenant_id
from app.models.api_key import ApiKey
from app.models.tenant_user import TenantUser
from app.repositories.base import BaseRepository

PREFIX = "rpt_"
# A person rarely needs more than one per assistant; the cap keeps a leaked session from minting
# keys by the hundred.
MAX_ACTIVE_KEYS_PER_USER = 10
# last_used_at is a hint for the panel ("used 3 minutes ago"), not an audit trail: writing it on
# every request would turn each read into a write.
_TOUCH_AFTER = timedelta(minutes=5)
_SHOWN_CHARS = 12  # "rpt_" and 8 characters of the secret: enough to tell keys apart, useless alone


# Neither revoked nor past its expiry, on the database's clock: what authenticates and what counts
# towards the cap, so a dead key never blocks its person from making a new one.
_LIVE: ColumnElement[bool] = ApiKey.revoked_at.is_(None) & (ApiKey.expires_at.is_(None) | (ApiKey.expires_at > func.now()))


@dataclass(frozen=True)
class NewKey:
    key: ApiKey
    secret: str  # shown once to whoever made it, never stored


@dataclass(frozen=True)
class Principal:
    """Who is calling with a key: plain values, so it outlives the session that checked the key."""

    key_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


async def create(db: AsyncSession, user: TenantUser, name: str, expires_in_days: int | None) -> NewKey:
    """Makes a key for `user` (added to `db`, not committed) that expires `expires_in_days` from now,
    on the database's clock, or never with None. The API allows only 30, 90 or 365 days."""
    tenant_id = require_tenant_id(user)
    active = await db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id, _LIVE))
    if (active or 0) >= MAX_ACTIVE_KEYS_PER_USER:
        raise ValidationException(f"You already have {MAX_ACTIVE_KEYS_PER_USER} keys: revoke one you no longer use")
    secret = PREFIX + secrets.token_urlsafe(32)  # 256 random bits
    key = ApiKey(
        tenant_id=tenant_id, user_id=user.id, name=name, key_hash=_hash(secret), prefix=secret[:_SHOWN_CHARS],
        expires_at=None if expires_in_days is None else func.now() + timedelta(days=expires_in_days),
    )
    db.add(key)
    await db.flush()
    return NewKey(key=key, secret=secret)


async def visible_keys(db: AsyncSession, user: TenantUser) -> list[tuple[ApiKey, str]]:
    """The keys `user` may see, with their owner's name: a company admin sees the company's, so they
    can find and revoke a key a former colleague left behind; everyone else, their own."""
    query = (
        select(ApiKey, TenantUser.full_name)
        .join(TenantUser, ApiKey.user_id == TenantUser.id)
        .where(ApiKey.tenant_id == require_tenant_id(user))
        .order_by(ApiKey.created_at.desc())
    )
    if user.role != "tenant_admin":
        query = query.where(ApiKey.user_id == user.id)
    return [(key, owner) for key, owner in (await db.execute(query)).all()]


async def revocable_key(db: AsyncSession, user: TenantUser, key_id: uuid.UUID) -> ApiKey:
    """A key `user` may revoke: their own, or any of the company's for its admin. Anything else is a
    404, as if it did not exist (another company's key, or a colleague's for a non-admin)."""
    key = await get_scoped_or_404(BaseRepository(ApiKey, db), key_id, tenant_id=require_tenant_id(user))
    if key.user_id != user.id and user.role != "tenant_admin":
        raise ResourceNotFoundException()
    return key


async def revoke_all(db: AsyncSession, user: TenantUser) -> int:
    """Revokes every key of `user` not yet revoked, expired ones too (not committed), and says how
    many: signing someone out everywhere also ends any key a stolen session may have made."""
    result = await db.execute(
        update(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)).values(revoked_at=func.now())
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


async def authenticate(db: AsyncSession, secret: str) -> Principal | None:
    """The person a key acts as, or None: an unknown, revoked or expired key, or a person who may not act
    (inactive, company suspended, the read-only public demo account). Commits when it records the
    key's use."""
    if not secret.startswith(PREFIX) or len(secret) > 100:
        return None
    key = await db.scalar(select(ApiKey).where(ApiKey.key_hash == _hash(secret), _LIVE))
    if key is None:
        return None
    user = await db.get(TenantUser, key.user_id)
    if user is None or user.tenant_id != key.tenant_id or not await can_sign_in(db, user) or is_demo_user(user):
        return None
    principal = Principal(key_id=key.id, user_id=user.id, tenant_id=key.tenant_id)
    # A conditional UPDATE, so two simultaneous requests don't both write it.
    touched = await db.execute(
        update(ApiKey)
        .where(
            ApiKey.id == key.id,
            (ApiKey.last_used_at.is_(None)) | (ApiKey.last_used_at < func.now() - _TOUCH_AFTER),
        )
        .values(last_used_at=func.now())
    )
    if touched.rowcount:  # type: ignore[attr-defined]
        await db.commit()
    return principal
