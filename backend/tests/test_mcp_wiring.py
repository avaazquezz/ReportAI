"""The MCP endpoint as the running API serves it: built by the app's own lifespan, not by a test
fixture (tests/test_mcp_server.py starts it by hand for each test)."""

import httpx2
import pytest

from app.main import app
from app.services import instance_settings


async def test_the_api_s_lifespan_starts_the_mcp_server(own_sessions: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing_saved(session: object = None) -> dict[str, str]:
        return {}

    monkeypatch.setattr(instance_settings, "load", nothing_saved)

    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test")
    async with app.router.lifespan_context(app), http:
        response = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    # Without the lifespan the endpoint has no server behind it and the request is a 500.
    assert response.status_code == 401
