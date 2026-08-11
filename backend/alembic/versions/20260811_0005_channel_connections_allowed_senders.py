"""channel connections allowed senders

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channel_connections",
        sa.Column(
            "allowed_senders",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("channel_connections", "allowed_senders")
