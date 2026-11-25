"""What an AI assistant calls the MCP server with: a personal API key (services/api_keys.py) or an
app the person connected by signing in (services/oauth/). Either acts as its person, and only while
that person may act: the one check below, shared by both, so neither can drift from the other."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import can_sign_in, is_demo_user
from app.models.tenant_user import TenantUser

CredentialKind = Literal["api_key", "oauth"]


@dataclass(frozen=True)
class Credential:
    """Which credential: an API key's id, or an OAuth grant's (the connection an app holds)."""

    kind: CredentialKind
    id: uuid.UUID


@dataclass(frozen=True)
class Principal:
    """Who is calling, and with what: plain values, so it outlives the session that checked it."""

    credential: Credential
    user_id: uuid.UUID
    tenant_id: uuid.UUID


async def acting_person(db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> TenantUser | None:
    """The person a credential acts as, or None when they may not act now: gone, moved out of the
    company the credential belongs to, unable to sign in (inactive, company suspended) or the
    read-only public demo account."""
    user = await db.get(TenantUser, user_id)
    if user is None or user.tenant_id != tenant_id or not await can_sign_in(db, user) or is_demo_user(user):
        return None
    return user
