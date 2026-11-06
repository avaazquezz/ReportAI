"""tenants.deletion_requested_at: when a company asked to be deleted (purged after a grace period)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No company has asked yet: none is ever purged by this migration.
    op.add_column("tenants", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "deletion_requested_at")
