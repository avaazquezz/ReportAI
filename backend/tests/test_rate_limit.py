"""SEC-3: login and password reset had no attempt limit at all; then the limit lived in each\nprocess's memory, so two API workers doubled it and a restart reset it."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import rate_limit
from app.core.exceptions import RateLimitException
from app.core.rate_limit import AttemptLimiter
from app.core.security import hash_password
from app.models.rate_limit_hit import RateLimitHit
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


async def test_limiter_blocks_after_max_attempts_and_frees_after_the_window(db: AsyncSession) -> None:
    limiter = AttemptLimiter("t", max_attempts=2, window_seconds=60)

    await limiter.record(db, "k")
    await limiter.record(db, "k")
    with pytest.raises(RateLimitException) as blocked:
        await limiter.check(db, "k")
    assert blocked.value.status_code == 429
    assert 58 <= int(blocked.value.headers["Retry-After"]) <= 60

    await limiter.check(db, "other-key")  # keys are independent
    await AttemptLimiter("other-limiter", max_attempts=2, window_seconds=60).check(db, "k")  # so are limiters
    await db.execute(update(RateLimitHit).values(at=func.now() - timedelta(seconds=61)))
    await limiter.check(db, "k")  # window elapsed


async def test_every_api_worker_sees_the_same_count(db: AsyncSession, _test_engine: AsyncEngine) -> None:
    # Two uvicorn workers are two processes with their own sessions: the count lives in Postgres.
    limiter = AttemptLimiter("t", max_attempts=1, window_seconds=60)
    other_worker = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

    async with other_worker() as session:
        await limiter.record(session, "k")

    with pytest.raises(RateLimitException):
        await limiter.check(db, "k")


async def test_an_attempt_still_counts_when_the_request_then_fails(db: AsyncSession) -> None:
    # A failed login raises right after recording, and get_db rolls the request back.
    limiter = AttemptLimiter("t", max_attempts=1, window_seconds=60)

    await limiter.record(db, "k")
    await db.rollback()

    with pytest.raises(RateLimitException):
        await limiter.check(db, "k")


async def test_maintenance_prunes_only_old_attempts(db: AsyncSession) -> None:
    limiter = AttemptLimiter("t", max_attempts=1, window_seconds=60)
    await limiter.record(db, "recent")
    db.add(RateLimitHit(key="t:old", at=datetime.now(UTC) - rate_limit.KEEP_HITS_FOR - timedelta(minutes=1)))
    await db.commit()

    await rate_limit.prune(db)

    assert list((await db.execute(select(RateLimitHit.key))).scalars()) == ["t:recent"]


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
