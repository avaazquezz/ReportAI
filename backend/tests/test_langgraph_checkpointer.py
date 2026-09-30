import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import langgraph_checkpointer as checkpointer_module
from app.core.config import settings


async def test_init_fails_fast_until_the_migrate_step_has_run(monkeypatch: pytest.MonkeyPatch) -> None:
    scratch_db = f"reportai_ckpt_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{scratch_db}"'))
    monkeypatch.setattr(settings, "POSTGRES_DB", scratch_db)
    try:
        with pytest.raises(RuntimeError, match="checkpoint tables are missing"):
            await checkpointer_module.init_checkpointer()

        await checkpointer_module.setup_checkpointer_schema()
        await checkpointer_module.setup_checkpointer_schema()  # re-running a deploy must be a no-op

        saver = await checkpointer_module.init_checkpointer()
        assert saver is checkpointer_module.get_checkpointer()
    finally:
        await checkpointer_module.close_checkpointer()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_db}" WITH (FORCE)'))
        await admin.dispose()
