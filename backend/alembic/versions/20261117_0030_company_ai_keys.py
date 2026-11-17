"""company_settings, tenants.platform_ai, execution_logs.platform_key: each company's own AI keys

On the hosted service a company enters its own AI provider and key; the platform's key serves
only the companies the super admin marks. Companies that exist today keep the platform's AI
(platform_ai = true), so nothing changes for them. Every AI call logged so far was paid by the
platform (platform_key = true); a call made with a company's own key says so, and the platform's
spend breaker leaves it out.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_settings",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "key"),
    )
    op.add_column("tenants", sa.Column("platform_ai", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute("UPDATE tenants SET platform_ai = true")
    op.add_column("execution_logs", sa.Column("platform_key", sa.Boolean(), server_default=sa.true(), nullable=False))
    # The breaker sums today's platform-paid cost on every message.
    op.create_index(
        "ix_execution_logs_platform_created_at", "execution_logs", ["created_at"],
        postgresql_where=sa.text("platform_key"),
    )


def downgrade() -> None:
    op.drop_index("ix_execution_logs_platform_created_at", table_name="execution_logs")
    op.drop_column("execution_logs", "platform_key")
    op.drop_column("tenants", "platform_ai")
    op.drop_table("company_settings")
