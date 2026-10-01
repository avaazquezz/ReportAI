"""tenants.brand_color and tenants.logo_path: the company's look on emails and documents

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-01

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("brand_color", sa.String(7), nullable=True))
    op.add_column("tenants", sa.Column("logo_path", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "logo_path")
    op.drop_column("tenants", "brand_color")
