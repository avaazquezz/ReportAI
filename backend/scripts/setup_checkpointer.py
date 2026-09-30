"""Creates/upgrades LangGraph's checkpoint tables. Run after `alembic upgrade head` on every
deploy — the prod compose's `migrate` service does both (`make migrate` does both in dev).

Usage: python scripts/setup_checkpointer.py
"""

import asyncio

from app.core.langgraph_checkpointer import setup_checkpointer_schema

if __name__ == "__main__":
    asyncio.run(setup_checkpointer_schema())
