"""The company's audit log, for its admins: who signed in, invited, changed a role, a channel or
a setting, and when. Newest first."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant_admin
from app.core.scoping import require_tenant_id
from app.models.audit_event import AuditEvent
from app.models.tenant_user import TenantUser
from app.schemas.audit import AuditEventResponse
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/audit", tags=["admin:audit"])


@router.get("")
async def list_audit_events(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = Query(default=None, max_length=64, description="Only actions starting with this, e.g. auth."),
    current_user: TenantUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AuditEventResponse]:
    tenant_id = require_tenant_id(current_user)
    where = [AuditEvent.tenant_id == tenant_id]
    if action:
        where.append(AuditEvent.action.startswith(action, autoescape=True))  # "_" is literal, not a wildcard
    total = await db.scalar(select(func.count()).select_from(AuditEvent).where(*where))
    events = await db.scalars(
        select(AuditEvent).where(*where).order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset(skip).limit(limit)
    )
    return PaginatedResponse(
        items=[AuditEventResponse.model_validate(e) for e in events], total=total or 0, skip=skip, limit=limit
    )
