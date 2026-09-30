from collections.abc import AsyncGenerator
from typing import Any

from httpx import AsyncClient

from app.core.database import get_db
from app.main import app


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_health_returns_503_when_the_database_is_down(client: AsyncClient) -> None:
    class _BrokenSession:
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("database is down")

    async def _broken_db() -> AsyncGenerator[_BrokenSession, None]:
        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken_db

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["database"] == "down"
