"""password_reset_tokens.purpose + code_hash (technicians' magic links); tenant_users.email_verified_at

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "password_reset_tokens", sa.Column("purpose", sa.String(16), nullable=False, server_default="reset")
    )
    op.add_column("password_reset_tokens", sa.Column("code_hash", sa.String(64), nullable=True))
    op.add_column("tenant_users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Everyone so far predates verification: never treat them as a fresh, unconfirmed signup.
    op.execute("UPDATE tenant_users SET email_verified_at = created_at")


def downgrade() -> None:
    op.drop_column("tenant_users", "email_verified_at")
    op.drop_column("password_reset_tokens", "code_hash")
    op.drop_column("password_reset_tokens", "purpose")
