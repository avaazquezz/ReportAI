"""document templates upload metadata

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_templates",
        sa.Column("original_filename", sa.String(length=500), server_default="", nullable=False),
    )
    op.add_column(
        "document_templates",
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_templates_uploaded_by_tenant_users",
        "document_templates",
        "tenant_users",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_templates_uploaded_by_tenant_users", "document_templates", type_="foreignkey"
    )
    op.drop_column("document_templates", "uploaded_by")
    op.drop_column("document_templates", "original_filename")
