"""First run of a fresh installation: whoever installed it gets a one-time code in the terminal,
and the panel's setup wizard asks for it before letting anyone create the company and its admin.

Without the code, the first visitor of a just-installed server — anyone who found its address —
would become its administrator."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.tenant_user import TenantUser
from app.services import instance_settings

SETUP_CODE_TTL = timedelta(hours=24)
# No 0/O, 1/I/L: the code is read off a terminal and typed by hand.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_HASH_KEY, _EXPIRES_KEY = "setup_code_hash", "setup_code_expires_at"


def _normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _hash(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode()).hexdigest()


async def needs_setup(session: AsyncSession) -> bool:
    """A one-company installation nobody has set up yet: it has no users at all."""
    return settings.SINGLE_TENANT and not await session.scalar(select(exists().where(TenantUser.id.is_not(None))))


async def issue_setup_code(session: AsyncSession) -> str:
    """A new code, replacing any earlier one. Only its hash is stored."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    expires = datetime.now(UTC) + SETUP_CODE_TTL
    await instance_settings.save(session, {_HASH_KEY: _hash(raw), _EXPIRES_KEY: expires.isoformat()})
    return "-".join(raw[i : i + 4] for i in range(0, 12, 4))


async def code_is_valid(session: AsyncSession, code: str) -> bool:
    stored = await instance_settings.load(session)
    expected, expires = stored.get(_HASH_KEY), stored.get(_EXPIRES_KEY)
    if not expected or not expires or datetime.fromisoformat(expires) < datetime.now(UTC):
        return False
    return secrets.compare_digest(expected, _hash(code))


async def consume_setup_code(session: AsyncSession) -> None:
    await instance_settings.save(session, {_HASH_KEY: "", _EXPIRES_KEY: ""})
