"""reports.requester_user_id: the signed-in person (a technician) who captured a report

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "requester_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_reports_tenant_id_requester_user_id", "reports", ["tenant_id", "requester_user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_reports_tenant_id_requester_user_id", table_name="reports")
    op.drop_column("reports", "requester_user_id")
