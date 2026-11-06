"""The audit log: who did something security-relevant (signed in, changed a role, a key, a
plan), to what, when and from where — so a company's admin, support or an incident review can
answer "who changed this?". Each event is added to the caller's session and commits with the
change it describes. Secrets never go in: for a settings change, only which fields changed."""

import uuid
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.tenant_user import TenantUser

# Long enough for a yearly review; the worker deletes what is older.
KEEP_EVENTS_FOR = timedelta(days=365)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """The names of the fields `after` gives a new value. Names only: a new API key or password
    is recorded as changed, never as what it is. A field missing from `before` counts as ""."""
    return sorted(key for key, value in after.items() if before.get(key, "") != value)


async def record(
    db: AsyncSession,
    action: str,
    *,
    actor: TenantUser | None = None,
    tenant_id: uuid.UUID | None = None,
    target: object = None,
    request: Request | None = None,
    actor_label: str | None = None,
    **details: Any,
) -> None:
    """Adds one event to `db` (no commit). The company defaults to the actor's; the label to the
    actor's email (pass actor_label="system" for what nobody signed in did)."""
    db.add(
        AuditEvent(
            tenant_id=tenant_id or (actor.tenant_id if actor else None),
            actor_id=actor.id if actor else None,
            actor_label=actor.email if actor else actor_label,
            action=action,
            target=str(target) if target is not None else None,
            ip=client_ip(request) if request else None,
            details=details or None,
        )
    )


async def prune(db: AsyncSession) -> None:
    await db.execute(delete(AuditEvent).where(AuditEvent.created_at < func.now() - KEEP_EVENTS_FOR))
