import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Separate driver/pool from SQLAlchemy's asyncpg engine, both pointed at the
# same database — langgraph-checkpoint-postgres requires psycopg, not asyncpg.
_pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] | None = None
_checkpointer: AsyncPostgresSaver | None = None


def _dsn() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


async def setup_checkpointer_schema() -> None:
    """Create or upgrade LangGraph's checkpoint tables. Run once per deploy by the
    `migrate` service (scripts/setup_checkpointer.py), never from the app's startup.

    AsyncPostgresSaver.setup() issues `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX
    CONCURRENTLY IF NOT EXISTS` with no locking of its own, so two processes running it
    on a fresh database race on Postgres's implicit row type. Serializing them with an
    advisory lock doesn't work either: the lock holder's CONCURRENTLY index build waits
    for every other open statement, including the waiter blocked on that very lock.
    Running it from a single one-shot process avoids both problems."""
    conn = await AsyncConnection.connect(_dsn(), autocommit=True, row_factory=dict_row)
    try:
        await AsyncPostgresSaver(conn).setup()
    finally:
        await conn.close()


async def init_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer
    _pool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
        _dsn(),
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
        # Without a check, connections that died while idle (Postgres restarted, a proxy
        # dropped them) are handed out as-is and the first calls on them fail.
        check=AsyncConnectionPool.check_connection,
        open=False,
    )
    await _pool.open()
    try:
        async with _pool.connection() as conn:
            cursor = await conn.execute("SELECT to_regclass('checkpoint_migrations')")
            row = await cursor.fetchone()
        if row is None or row["to_regclass"] is None:
            raise RuntimeError(
                "LangGraph checkpoint tables are missing. They are created by the migrate step "
                "(`python scripts/setup_checkpointer.py`), which must run before the app starts."
            )
    except Exception:
        await _pool.close()
        _pool = None
        raise
    _checkpointer = AsyncPostgresSaver(_pool)
    return _checkpointer


async def close_checkpointer() -> None:
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized — init_checkpointer() must run in app startup/lifespan")
    return _checkpointer
