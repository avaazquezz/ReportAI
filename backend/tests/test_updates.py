"""Whoever runs the installation is told when a newer release is out, and — loudly — when a
published security advisory affects the release it runs."""

from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.services import updates
from app.services.updates import affecting, parse_version, update_status

ADVISORIES = {
    "advisories": [
        {"id": "RAI-1", "title": "Old bug", "severity": "high", "fixed_in": "0.2.0"},
        {"id": "RAI-2", "title": "Token leak", "severity": "critical", "introduced": "0.2.0", "fixed_in": "0.3.1", "url": "https://x"},
        {"id": "RAI-3", "title": "Future", "severity": "low", "introduced": "0.4.0", "fixed_in": "0.4.2"},
    ]
}


def test_release_numbers_compare_as_numbers() -> None:
    assert parse_version("v0.10.0") == (0, 10, 0) > parse_version("0.9.9")  # type: ignore[operator]
    assert parse_version("dev") is None and parse_version("") is None


def test_only_the_advisories_covering_this_release_apply() -> None:
    assert [a.id for a in affecting(ADVISORIES["advisories"], "0.3.0")] == ["RAI-2"]
    assert [a.id for a in affecting(ADVISORIES["advisories"], "0.1.5")] == ["RAI-1"]
    assert affecting(ADVISORIES["advisories"], "0.3.1") == []
    assert affecting(ADVISORIES["advisories"], "dev") == []  # a dev build is not a release


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"tag_name": "v0.3.1", "html_url": "https://github.com/r/releases/v0.3.1"})
        return httpx.Response(200, json=ADVISORIES)

    real = httpx.AsyncClient
    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "REPORTAI_VERSION", "0.3.0")
    monkeypatch.setattr(settings, "UPDATE_CHECK_ENABLED", True)
    updates.clear_cache()
    yield asked
    updates.clear_cache()


async def test_a_newer_release_and_an_advisory_are_reported_and_cached(github: list[str]) -> None:
    status = await update_status()

    assert (status.current, status.latest, status.update_available) == ("0.3.0", "0.3.1", True)
    assert [a.id for a in status.advisories] == ["RAI-2"]
    await update_status()
    assert len(github) == 2  # asked once; the second answer came from the cache


async def test_github_being_down_never_breaks_the_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    real = httpx.AsyncClient
    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    updates.clear_cache()

    status = await update_status()

    assert status.error and not status.update_available
    updates.clear_cache()


async def test_the_installations_admin_sees_it_in_the_panel(
    client: AsyncClient, db: AsyncSession, github: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SINGLE_TENANT", True)
    tenant = Tenant(name="A", slug="a", is_active=True)
    db.add(tenant)
    await db.flush()
    db.add(TenantUser(tenant_id=tenant.id, email="a@a.test", hashed_password=hash_password("pw-12345678"), full_name="A", role="tenant_admin"))
    await db.commit()
    login = await client.post("/auth/login", json={"email": "a@a.test", "password": "pw-12345678"})

    version = await client.get("/instance/version", headers={"Authorization": f"Bearer {login.json()['access_token']}"})

    assert version.json()["update_available"] is True and version.json()["advisories"][0]["severity"] == "critical"
    assert (await client.get("/health")).json()["version"] == "0.3.0"
