import uuid
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from app.core.exceptions import AuthorizationException, ResourceNotFoundException
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    from app.models.tenant_user import TenantUser


class _HasTenantId(Protocol):
    id: Any
    tenant_id: Any


ScopedModel = TypeVar("ScopedModel", bound=_HasTenantId)


def require_tenant_id(user: "TenantUser") -> uuid.UUID:
    """Narrow TenantUser.tenant_id (nullable for super_admin rows) to a concrete UUID for
    routes that only make sense for a tenant-scoped caller. require_tenant_admin permits
    super_admin too, so this is the guard for the (unreachable-via-the-UI, but
    API-reachable) case of a super_admin calling a tenant-owned-resource endpoint."""
    if user.tenant_id is None:
        raise AuthorizationException("This action requires a tenant-scoped account")
    return user.tenant_id


async def get_scoped_or_404(
    repo: BaseRepository[ScopedModel], id_: uuid.UUID, *, tenant_id: uuid.UUID
) -> ScopedModel:
    """Fetch a tenant-owned row by id, or 404 — never 403 — if it's missing or belongs to
    another tenant. A 403 would confirm the id exists on someone else's tenant."""
    obj = await repo.get_by_id(id_)
    if obj is None or obj.tenant_id != tenant_id:
        raise ResourceNotFoundException()
    return obj
