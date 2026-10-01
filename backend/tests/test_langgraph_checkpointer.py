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


def test_the_graph_state_survives_a_checkpoint_round_trip_and_other_classes_do_not(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """What a paused report carries — asyncpg's own UUIDs from the ORM, the document-type choices —
    must read back intact; a class nobody listed must not be instantiated from a checkpoint row."""
    from datetime import UTC, datetime

    from asyncpg.pgproto.pgproto import UUID as AsyncpgUUID
    from pydantic import BaseModel

    from app.services.agent.state import DocumentTypeOption

    serde = checkpointer_module.CHECKPOINT_SERDE
    report_id = AsyncpgUUID(str(uuid.uuid4()))
    state = {
        "report_id": report_id,
        "received_at": datetime(2026, 3, 12, 9, 15, tzinfo=UTC),
        "available_document_types": [DocumentTypeOption(id=uuid.uuid4(), name="Acta")],
    }

    restored = serde.loads_typed(serde.dumps_typed(state))

    assert restored == state and restored["report_id"] == report_id
    assert isinstance(restored["available_document_types"][0], DocumentTypeOption)
    assert not any("Blocked" in record.getMessage() for record in caplog.records)

    class Intruder(BaseModel):
        payload: str

    assert not isinstance(serde.loads_typed(serde.dumps_typed(Intruder(payload="x"))), Intruder)
