"""execution logs tenant/created_at composite index

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_execution_logs_tenant_id_created_at",
        "execution_logs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_logs_tenant_id_created_at", table_name="execution_logs")
