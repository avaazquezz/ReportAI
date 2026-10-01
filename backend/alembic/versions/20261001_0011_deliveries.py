"""deliveries: what was sent, to whom, and whether it arrived

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),  # channel | email
        sa.Column("destination", sa.String(320), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),  # pending | sent | failed
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("report_id", "kind", "destination", name="uq_deliveries_report_kind_destination"),
    )
    op.create_index("ix_deliveries_report_id", "deliveries", ["report_id"])


def downgrade() -> None:
    op.drop_table("deliveries")
