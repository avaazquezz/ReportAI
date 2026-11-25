"""api_keys.expires_at: a personal key may expire after 30, 90 or 365 days

Optional: NULL is a key that never expires, which every existing key stays, so nothing that works
today stops working. A nullable column with no default is metadata only: no table rewrite.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-25

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
