"""widen reports.status to fit pause statuses

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # "awaiting_doctype_selection" is 26 chars — String(20) would reject the write.
    op.alter_column(
        "reports",
        "status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "reports",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(30),
        existing_nullable=False,
    )
