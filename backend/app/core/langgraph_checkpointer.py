from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

# Separate driver/pool from SQLAlchemy's asyncpg engine, both pointed at the
# same database — langgraph-checkpoint-postgres requires psycopg, not asyncpg.
_pool: AsyncConnectionPool[AsyncConnection[dict[str, Any]]] | None = None
_checkpointer: AsyncPostgresSaver | None = None


def _dsn() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


async def init_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer
    _pool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
        _dsn(),
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # idempotent — creates LangGraph's own checkpoint tables if missing
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
