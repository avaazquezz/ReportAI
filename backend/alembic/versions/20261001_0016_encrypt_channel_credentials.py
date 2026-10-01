"""channel credentials encrypted at rest; webhooks route on a plain routing_key

The bot tokens and access tokens in channel_connections.credentials become one encrypted string
(app.core.crypto). The two values a shared webhook looks a connection up by — WhatsApp's
phone_number_id and the email inbound slug — move to routing_key, which is not secret.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-01

"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.crypto import decrypt, encrypt

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("channel_connections", sa.Column("routing_key", sa.String(255), nullable=True))
    op.execute(
        """
        UPDATE channel_connections SET routing_key = CASE channel_type
            WHEN 'whatsapp' THEN credentials->>'phone_number_id'
            WHEN 'email' THEN credentials->>'inbound_slug'
        END
        """
    )
    op.create_unique_constraint(
        "uq_channel_connections_type_routing_key", "channel_connections", ["channel_type", "routing_key"]
    )

    op.add_column("channel_connections", sa.Column("credentials_encrypted", sa.Text(), nullable=True))
    connection = op.get_bind()
    for row in connection.execute(sa.text("SELECT id, credentials FROM channel_connections")).all():
        connection.execute(
            sa.text("UPDATE channel_connections SET credentials_encrypted = :value WHERE id = :id"),
            {"value": encrypt(json.dumps(row.credentials)), "id": row.id},
        )
    op.drop_column("channel_connections", "credentials")
    op.alter_column("channel_connections", "credentials_encrypted", new_column_name="credentials", nullable=False)


def downgrade() -> None:
    op.add_column(
        "channel_connections",
        sa.Column("credentials_plain", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.text("SELECT id, credentials FROM channel_connections")).all():
        connection.execute(
            sa.text("UPDATE channel_connections SET credentials_plain = CAST(:value AS jsonb) WHERE id = :id"),
            {"value": decrypt(row.credentials), "id": row.id},
        )
    op.drop_column("channel_connections", "credentials")
    op.alter_column("channel_connections", "credentials_plain", new_column_name="credentials", nullable=False)
    op.drop_constraint("uq_channel_connections_type_routing_key", "channel_connections")
    op.drop_column("channel_connections", "routing_key")
