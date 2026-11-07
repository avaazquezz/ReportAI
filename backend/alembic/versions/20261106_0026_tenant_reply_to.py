"""tenants.reply_to_email: where replies to a company's emails go

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing companies have none: their emails carry no Reply-To, as before.
    op.add_column("tenants", sa.Column("reply_to_email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "reply_to_email")
