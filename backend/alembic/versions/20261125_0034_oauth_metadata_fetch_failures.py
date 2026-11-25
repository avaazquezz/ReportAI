"""oauth_metadata_fetch_failures: remember a client metadata document that failed to fetch

A client known by the URL of its metadata document (CIMD) is fetched on a stranger's say-so; one
whose address fails (down, slow, refused) is remembered for ten minutes so it is not fetched again
on every request. A new table only: nothing existing changes, and with MCP_OAUTH_ENABLED off it
stays empty.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-25

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_metadata_fetch_failures",
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("url"),
    )


def downgrade() -> None:
    op.drop_table("oauth_metadata_fetch_failures")
