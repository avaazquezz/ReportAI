"""tenants.plan*: the plan, its status and period; reports index for the quota count

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing companies stay as they are: unlimited and active.
    op.add_column("tenants", sa.Column("plan", sa.String(32), nullable=False, server_default="unlimited"))
    op.add_column("tenants", sa.Column("plan_status", sa.String(16), nullable=False, server_default="active"))
    op.add_column("tenants", sa.Column("plan_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("plan_period_end", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_reports_tenant_id_created_at", "reports", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_tenant_id_created_at", table_name="reports")
    op.drop_column("tenants", "plan_period_end")
    op.drop_column("tenants", "plan_period_start")
    op.drop_column("tenants", "plan_status")
    op.drop_column("tenants", "plan")
