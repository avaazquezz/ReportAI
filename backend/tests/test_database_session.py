"""A request's writes are committed before its response leaves: a client that reads back what it
was just told exists must find it, and a commit that fails must fail the request, not follow a 2xx.

FastAPI runs a `yield` dependency's exit code after sending the response unless it is declared
`scope="function"`; `get_db` commits in that exit code."""

import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import BaseRoute
from starlette.types import Message

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.document_type import DocumentType
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


def _sessions(dependant: Dependant) -> list[Dependant]:
    found = [dependant] if dependant.call is get_db else []
    for sub in dependant.dependencies:
        found += _sessions(sub)
    return found


def _api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    # Included routers stay nested in app.routes (FastAPI keeps each as one entry wrapping its
    # router), so walk into anything that carries a router of its own.
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif (router := getattr(route, "original_router", None)) is not None:
            yield from _api_routes(router.routes)


def test_every_route_commits_its_session_before_it_responds() -> None:
    routes = list(_api_routes(app.routes))
    with_a_session = [route for route in routes if _sessions(route.dependant)]
    late = sorted(
        {
            f"{', '.join(sorted(route.methods))} {route.path}"
            for route in with_a_session
            for session in _sessions(route.dependant)
            if session.scope != "function"
        }
    )
    assert len(with_a_session) > 80, "the walk no longer reaches the app's routes"
    assert not late, f'Declare Depends(get_db, scope="function") in: {late}'


@pytest.mark.usefixtures("own_sessions")
async def test_what_a_201_says_was_created_is_already_there_when_the_response_starts(
    db: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PATH", str(tmp_path))
    tenant = Tenant(name="Reformas García", slug=f"g-{uuid.uuid4().hex[:6]}", is_active=True, language="es")
    db.add(tenant)
    await db.flush()
    admin = TenantUser(
        tenant_id=tenant.id, email=f"a-{uuid.uuid4().hex[:6]}@garcia.test", hashed_password=hash_password("pw-12345678"),
        full_name="A", role="tenant_admin", is_active=True,
    )
    db.add(admin)
    await db.commit()
    token = create_access_token({"sub": str(admin.id), "role": admin.role, "tenant_id": str(tenant.id), "ver": admin.token_version})

    seen_at_response_start: list[int] = []
    status: list[int] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            status.append(message["status"])
            # Another connection, as the client's next request would use.
            async with AsyncSessionLocal() as other:
                count = await other.scalar(select(func.count()).select_from(DocumentType).where(DocumentType.tenant_id == tenant.id))
                seen_at_response_start.append(int(count or 0))

    scope: dict[str, Any] = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/starter-templates/work_order/install", "raw_path": b"/starter-templates/work_order/install",
        "root_path": "", "query_string": b"", "server": ("test", 80), "client": ("203.0.113.9", 1234),
        "headers": [(b"host", b"test"), (b"authorization", f"Bearer {token}".encode())],
    }
    await app(scope, receive, send)

    assert status == [201]
    assert seen_at_response_start == [1]
