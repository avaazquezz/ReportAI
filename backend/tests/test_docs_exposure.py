"""SEC-4: /docs, /redoc and /openapi.json listed every endpoint on production instances,
and GET / disclosed the environment name."""

import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app import main as main_module
from app.core.config import settings


async def _status_codes(paths: list[str]) -> dict[str, int]:
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return {path: (await client.get(path)).status_code for path in paths}


@pytest.fixture
def _reload_main_after(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    yield
    monkeypatch.undo()
    importlib.reload(main_module)


async def test_docs_are_closed_outside_development(
    monkeypatch: pytest.MonkeyPatch, _reload_main_after: None
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    importlib.reload(main_module)

    codes = await _status_codes(["/docs", "/redoc", "/openapi.json"])

    assert codes == {"/docs": 404, "/redoc": 404, "/openapi.json": 404}


async def test_docs_stay_available_in_development(
    monkeypatch: pytest.MonkeyPatch, _reload_main_after: None
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    importlib.reload(main_module)

    assert (await _status_codes(["/docs"]))["/docs"] == 200


async def test_root_does_not_reveal_the_environment() -> None:
    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = (await client.get("/")).json()

    assert body == {"service": "reportai-api"}
