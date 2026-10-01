"""report data for review (source text, fields, evidence) and per-tenant language/timezone

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("language", sa.String(5), server_default="es", nullable=False))
    op.add_column(
        "tenants", sa.Column("timezone", sa.String(64), server_default="Europe/Madrid", nullable=False)
    )

    # What the panel needs to review a report before approving it: until now the transcript
    # and extracted fields lived only inside the LangGraph checkpoint.
    op.add_column("reports", sa.Column("source_text", sa.Text(), nullable=True))
    op.add_column("reports", sa.Column("audio_path", sa.String(1024), nullable=True))
    op.add_column("reports", sa.Column("extracted_fields", postgresql.JSONB(), nullable=True))
    op.add_column("reports", sa.Column("evidence", postgresql.JSONB(), nullable=True))
    op.add_column("reports", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("reject_reason", sa.Text(), nullable=True))
    # Which connection the request came in on, so a worker (not the webhook) can answer it.
    op.add_column(
        "reports",
        sa.Column(
            "channel_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channel_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Channel-specific reply context, e.g. the Message-Id to thread an email answer under.
    op.add_column("reports", sa.Column("channel_meta", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for column in (
        "channel_meta", "channel_connection_id", "reject_reason", "received_at",
        "evidence", "extracted_fields", "audio_path", "source_text",
    ):
        op.drop_column("reports", column)
    op.drop_column("tenants", "timezone")
    op.drop_column("tenants", "language")
