from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  — registers all tables on Base.metadata
from app.core import rate_limit
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, get_db
from app.main import app
from app.services import instance_settings

TEST_DATABASE_URL = settings.DATABASE_URL.rsplit("/", 1)[0] + f"/{settings.POSTGRES_DB}_test"


@pytest_asyncio.fixture(scope="session")
async def _test_engine() -> AsyncGenerator:
    # NullPool avoids asyncpg's event-loop-binding issue across pytest-asyncio tests.
    admin_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{settings.POSTGRES_DB}_test"'))
        await conn.execute(text(f'CREATE DATABASE "{settings.POSTGRES_DB}_test"'))
    await admin_engine.dispose()

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db(_test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        # TRUNCATE everything between tests so each test starts from a clean slate.
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
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
def _fresh_rate_limits() -> None:
    rate_limit.clear_all()


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
