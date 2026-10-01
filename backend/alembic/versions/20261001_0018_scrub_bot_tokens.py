"""remove Telegram bot tokens from stored error messages

A failed call to Telegram used to be stored with httpx's message, which quotes the request URL —
and a Bot API URL contains the bot's token. The adapter no longer lets those messages out; this
cleans the ones already saved (shown in the panel as a delivery's or a report's error).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-01

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("deliveries", "last_error"),
    ("reports", "error_detail"),
    ("execution_logs", "error_detail"),
    ("jobs", "last_error"),
)


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = regexp_replace({column}, 'bot[0-9]+:[A-Za-z0-9_-]+', 'bot<token>', 'g') "
            f"WHERE {column} ~ 'bot[0-9]+:[A-Za-z0-9_-]+'"
        )


def downgrade() -> None:
    pass  # what was removed is not put back
