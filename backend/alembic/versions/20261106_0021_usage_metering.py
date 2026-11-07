"""execution_logs.input_tokens, output_tokens and audio_seconds: what each AI call used

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-06

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("execution_logs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("execution_logs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("execution_logs", sa.Column("audio_seconds", sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("execution_logs", "audio_seconds")
    op.drop_column("execution_logs", "output_tokens")
    op.drop_column("execution_logs", "input_tokens")
