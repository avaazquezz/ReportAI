import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  — registers all tables on Base.metadata
from app.core import security
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, get_db
from app.main import app
from app.services import company_ai, instance_settings

# bcrypt's minimum work factor: hashing or checking a password costs ~2 ms instead of ~0.4 s, and
# the logins in the suite add up to minutes. Set at import, before test modules hash at theirs.
assert security.BCRYPT_ROUNDS == 12, "production's bcrypt work factor changed"
security.BCRYPT_ROUNDS = 4

# One test database per checkout: runs in different worktrees against the same Postgres no longer
# drop each other's database mid-suite. Two runs in the same checkout still share it.
_CHECKOUT = hashlib.sha1(str(Path(__file__).resolve().parent).encode()).hexdigest()[:8]
TEST_DATABASE_NAME = f"{settings.POSTGRES_DB}_test_{_CHECKOUT}"
TEST_DATABASE_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + f"/{TEST_DATABASE_NAME}"


@pytest_asyncio.fixture(scope="session")
async def _test_engine() -> AsyncGenerator:
    # NullPool avoids asyncpg's event-loop-binding issue across pytest-asyncio tests.
    admin_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}"'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    # Each checkout has its own database: drop it, or every short-lived worktree leaves one behind.
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)'))
    await admin_engine.dispose()


@pytest_asyncio.fixture
async def db(_test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        # Empty every table between tests, children first, in one transaction. DELETE, not
        # TRUNCATE: on near-empty tables TRUNCATE pays a fixed cost per table (new files on disk),
        # ~1.4 s per test for 25 tables against ~0.1 s here. Commits stay real, so tests that read
        # from another connection (the worker, the queue) keep working.
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _open_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production rejects everyone when a channel's allow-list is empty; the tests that
    aren't about the allow-list use empty ones and expect messages through."""
    monkeypatch.setattr(settings, "ALLOW_ANY_SENDER", True)


@pytest.fixture(autouse=True)
def _channel_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """These are optional in production (empty disables the channel); the webhook tests need
    them set, whatever the environment they run in."""
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "test-whatsapp-app-secret")
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "test-whatsapp-verify-token")
    monkeypatch.setattr(settings, "MAILGUN_SIGNING_KEY", "test-mailgun-signing-key")


@pytest.fixture
def own_sessions(_test_engine):  # type: ignore[no-untyped-def]
    """Code outside a request (the worker, the queue, the nodes) opens its own sessions from
    AsyncSessionLocal; point that factory at the test database for the duration of a test."""
    original = AsyncSessionLocal.kw.get("bind")
    AsyncSessionLocal.configure(bind=_test_engine)
    yield
    AsyncSessionLocal.configure(bind=original)


@pytest.fixture(autouse=True)
def _nothing_saved_in_the_panel(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Instance settings are read from the database on every use. Outside the tests about them,
    nothing is saved in the panel and the environment decides — and no test reads whatever the
    development database happens to hold."""
    if "stored_instance_settings" in request.fixturenames:
        return

    async def nothing_saved(session: object = None) -> dict[str, str]:
        return {}

    monkeypatch.setattr(instance_settings, "load", nothing_saved)


@pytest.fixture
def stored_instance_settings(own_sessions: None) -> None:
    """Opt in to reading instance settings from the test database."""


@pytest.fixture(autouse=True)
def _installation_ai(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside the tests about companies' own AI keys, every company runs on the installation's
    AI, as before companies had keys of their own: the environment decides, and a node can run
    for a made-up company with no row behind it."""
    if "own_ai_keys" in request.fixturenames:
        return

    async def installation_extraction(_tenant_id: object) -> instance_settings.AIConfig:
        return instance_settings.ai_from(await instance_settings.load())

    async def installation_transcription(_tenant_id: object) -> instance_settings.TranscriptionConfig:
        return instance_settings.transcription_from(await instance_settings.load())

    monkeypatch.setattr(company_ai, "uses_own_keys", lambda tenant: False)
    monkeypatch.setattr(company_ai, "extraction_for", installation_extraction)
    monkeypatch.setattr(company_ai, "transcription_for", installation_transcription)


@pytest.fixture
def own_ai_keys(own_sessions: None) -> None:
    """Opt in: on the hosted service, a company uses its own AI keys unless it is on the
    platform's AI (services/company_ai.py)."""


@pytest.fixture(autouse=True)
def _telegram_tokens_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving a Telegram bot asks Telegram whether its token is real (getMe). Tests never reach
    Telegram: every token is a bot called @acme_bot unless a test says otherwise."""
    from app.api.admin import channel_connections

    async def accepted(bot_token: str) -> str:
        return "acme_bot"

    monkeypatch.setattr(channel_connections, "verify_telegram_bot", accepted)
