"""durable job queue, inbound message dedupe, report attachments, one active report per sender

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"])
    op.create_index("ix_jobs_report_id", "jobs", ["report_id"])

    # Webhooks are delivered at least once: Telegram, WhatsApp and Mailgun all retry. The unique
    # key is what turns a repeat into a no-op instead of a second report.
    op.create_table(
        "inbound_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channel_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_inbound_messages_connection_external"),
    )

    op.create_table(
        "report_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Null while the photo waits for the report it belongs to (people often send the
        # pictures before the voice note).
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("sender_identifier", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), server_default="photo", nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_report_attachments_report_id", "report_attachments", ["report_id"])
    op.create_index(
        "ix_report_attachments_waiting", "report_attachments", ["tenant_id", "sender_identifier"],
        postgresql_where=sa.text("report_id IS NULL"),
    )

    # A sender has at most one report in flight or waiting on them. The application checks
    # first; this is what makes it true when two messages arrive at the same instant.
    op.create_index(
        "uq_reports_one_active_per_sender",
        "reports",
        ["tenant_id", "requester_channel", "requester_identifier"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'awaiting_doctype_selection', 'awaiting_details', 'awaiting_approval')"),
    )


def downgrade() -> None:
    op.drop_index("uq_reports_one_active_per_sender", table_name="reports")
    op.drop_table("report_attachments")
    op.drop_table("inbound_messages")
    op.drop_table("jobs")
