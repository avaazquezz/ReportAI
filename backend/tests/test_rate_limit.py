"""SEC-3: login and password reset had no attempt limit at all."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.exceptions import RateLimitException
from app.core.rate_limit import AttemptLimiter
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser


async def _create_user(db: AsyncSession) -> TenantUser:
    tenant = Tenant(name="Acme", slug="acme", is_active=True)
    db.add(tenant)
    await db.flush()
    user = TenantUser(
        tenant_id=tenant.id,
        email="admin@acme.test",
        hashed_password=hash_password("correct-password"),
        full_name="Admin",
        role="tenant_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


def _login(client: AsyncClient, password: str, email: str = "admin@acme.test"):  # type: ignore[no-untyped-def]
    return client.post("/auth/login", json={"email": email, "password": password})


def test_limiter_blocks_after_max_attempts_and_frees_after_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1000.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: now[0])
    limiter = AttemptLimiter(max_attempts=2, window_seconds=60)

    limiter.record("k")
    limiter.record("k")
    with pytest.raises(RateLimitException) as blocked:
        limiter.check("k")
    assert blocked.value.status_code == 429
    assert blocked.value.headers == {"Retry-After": "60"}

    limiter.check("other-key")  # keys are independent
    now[0] += 61
    limiter.check("k")  # window elapsed


async def test_account_locks_after_five_wrong_passwords_even_for_the_right_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _create_user(db)
    for _ in range(5):
        assert (await _login(client, "wrong")).status_code == 401

    locked = await _login(client, "correct-password")

    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0


async def test_a_successful_login_clears_the_failure_count(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _create_user(db)
    for _ in range(4):
        await _login(client, "wrong")
    assert (await _login(client, "correct-password")).status_code == 200

    for _ in range(4):  # would be blocked already if the 4 earlier failures still counted
        assert (await _login(client, "wrong")).status_code == 401


async def test_one_ip_spraying_many_accounts_is_blocked(client: AsyncClient) -> None:
    for i in range(rate_limit.login_by_ip.max_attempts):
        assert (await _login(client, "x", email=f"user{i}@acme.test")).status_code == 401

    assert (await _login(client, "x", email="someone-else@acme.test")).status_code == 429


async def test_password_reset_requests_are_limited_per_email(client: AsyncClient) -> None:
    for _ in range(5):
        assert (
            await client.post("/auth/forgot-password", json={"email": "a@acme.test"})
        ).status_code == 200

    blocked = await client.post("/auth/forgot-password", json={"email": "a@acme.test"})

    assert blocked.status_code == 429
