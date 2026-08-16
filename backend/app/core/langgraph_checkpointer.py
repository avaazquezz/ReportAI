import asyncio
import contextlib
import hashlib
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

# Session-level Postgres advisory lock key serializing concurrent first-time
# runs of AsyncPostgresSaver.setup() across uvicorn worker processes (see
# _run_setup_under_lock() below for why this is needed). Derived once,
# deterministically, from a fixed namespaced string so it's reproducible and
# greppable rather than a bare magic number. `grep -rn pg_advisory` over the
# repo confirms nothing else here takes advisory locks, so this key has no
# in-repo collision risk.
_LOCK_NAMESPACE = b"reportai:langgraph_checkpointer_setup:v1"
_CHECKPOINTER_SETUP_LOCK_KEY = int.from_bytes(
    hashlib.sha256(_LOCK_NAMESPACE).digest()[:8], "big", signed=True
)

# How long a worker waits to acquire the setup lock before giving up. Generous
# because LangGraph's own MIGRATIONS list includes `CREATE INDEX CONCURRENTLY
# IF NOT EXISTS` statements that can legitimately take a while against a large
# pre-existing table — but bounded, so a genuinely stuck/dead peer can't hang
# every other worker's startup forever.
_SETUP_LOCK_TIMEOUT_SECONDS = 60.0


def _dsn() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


async def _run_setup_under_lock() -> None:
    """Run AsyncPostgresSaver.setup() serialized across uvicorn worker processes.

    setup() runs `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX CONCURRENTLY IF NOT
    EXISTS` statements on an autocommit connection with no locking of its own.
    `IF NOT EXISTS` is idempotent for repeat/sequential calls once the object
    exists, but is NOT safe under concurrent first-creation: two sessions can
    both pass the "does it exist" check before either commits, and one loses
    with a UniqueViolation on Postgres's implicit composite row type for the
    new table (the `pg_type_typname_nsp_index` unique index). backend/Dockerfile
    runs `uvicorn ... --workers 2`; each worker is a fully independent process
    that calls init_checkpointer() on its own, so on a fresh Postgres volume
    (first-ever deploy, or any deploy against a wiped database) this race is
    real and takes down whichever worker loses it.

    Fix: acquire a SESSION-level Postgres advisory lock
    (pg_advisory_lock/pg_advisory_unlock) and run setup() on that exact same
    connection, so the lock is held for that connection's entire lifetime and
    for the entire duration of setup() — there is no window in which the lock
    could be released while setup()'s DDL is still in flight on some other
    session.

    Deliberately SESSION-level, not pg_advisory_xact_lock: LangGraph's own
    MIGRATIONS list includes `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, and
    CONCURRENTLY cannot run inside a transaction block at all — an xact-scoped
    lock would force setup() onto a transaction and break that statement
    outright. The session-level lock has no such requirement: it's tied to
    this connection's backend PID, not to any transaction, so every statement
    setup() runs stays autocommit exactly as it does today.

    Winner: acquires the lock uncontended, runs the full migration loop,
    commits every statement, releases the lock. Loser(s): block on
    pg_advisory_lock until the winner's connection releases it (explicit
    unlock, or the connection closing — Postgres releases session-level
    advisory locks automatically on backend disconnect either way), then run
    setup() themselves — but by then `checkpoint_migrations` already has every
    row inserted by the winner, so AsyncPostgresSaver's own version check
    makes the loop a single no-op SELECT. No second caller ever races the DDL.

    If the lock can't be acquired within _SETUP_LOCK_TIMEOUT_SECONDS, the
    connection is closed and the timeout error propagates — that worker fails
    startup exactly as it does today for any other setup() error (Uvicorn
    kills it) rather than hanging forever.
    """
    conn = await AsyncConnection.connect(_dsn(), autocommit=True, row_factory=dict_row)
    try:
        try:
            await asyncio.wait_for(
                conn.execute(
                    "SELECT pg_advisory_lock(%s)", (_CHECKPOINTER_SETUP_LOCK_KEY,)
                ),
                timeout=_SETUP_LOCK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "Timed out after %.0fs waiting for the LangGraph checkpointer "
                "setup advisory lock (key=%d) — another worker may be stuck "
                "mid-setup(). Aborting this worker's startup.",
                _SETUP_LOCK_TIMEOUT_SECONDS,
                _CHECKPOINTER_SETUP_LOCK_KEY,
            )
            raise
        try:
            await AsyncPostgresSaver(conn).setup()
        finally:
            # Best-effort explicit unlock. If this fails because the session
            # is already dead, closing the connection below still releases
            # the lock server-side — Postgres cleans up session-level
            # advisory locks on backend disconnect.
            with contextlib.suppress(Exception):
                await conn.execute(
                    "SELECT pg_advisory_unlock(%s)", (_CHECKPOINTER_SETUP_LOCK_KEY,)
                )
    finally:
        await conn.close()


async def init_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer
    _pool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
        _dsn(),
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await _pool.open()
    # See _run_setup_under_lock()'s docstring: setup()'s own CREATE TABLE /
    # CREATE INDEX CONCURRENTLY "IF NOT EXISTS" statements are not safe under
    # concurrent first-creation, which this Dockerfile's `--workers 2` makes
    # possible on every fresh Postgres volume.
    await _run_setup_under_lock()
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
