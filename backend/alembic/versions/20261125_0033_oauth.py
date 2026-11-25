"""oauth_clients, oauth_codes, oauth_grants, oauth_tokens: OAuth sign-in for AI assistants

An AI client (claude.ai, ChatGPT, Cursor) connects to the MCP server by having the person sign in
and approve it, instead of pasting an API key. Codes and tokens are stored as SHA-256 hashes only.
Everything goes with its company and its person (CASCADE), and tokens with their grant. New tables
only: nothing existing changes, and with MCP_OAUTH_ENABLED off they stay empty.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('dcr', 'cimd')", name="ck_oauth_clients_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_table(
        "oauth_codes",
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("oauth_client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_explicit", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["oauth_client_id"], ["oauth_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["tenant_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_hash"),
    )
    op.create_index("ix_oauth_codes_expires_at", "oauth_codes", ["expires_at"])
    op.create_index("ix_oauth_codes_oauth_client_id", "oauth_codes", ["oauth_client_id"])
    op.create_index("ix_oauth_codes_tenant_id", "oauth_codes", ["tenant_id"])
    op.create_index("ix_oauth_codes_user_id", "oauth_codes", ["user_id"])
    op.create_table(
        "oauth_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("oauth_client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["oauth_client_id"], ["oauth_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["tenant_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_grants_oauth_client_id", "oauth_grants", ["oauth_client_id"])
    op.create_index("ix_oauth_grants_tenant_id", "oauth_grants", ["tenant_id"])
    op.create_index("ix_oauth_grants_user_id", "oauth_grants", ["user_id"])
    op.create_table(
        "oauth_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('access', 'refresh')", name="ck_oauth_tokens_kind"),
        sa.ForeignKeyConstraint(["grant_id"], ["oauth_grants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_oauth_tokens_expires_at", "oauth_tokens", ["expires_at"])
    op.create_index("ix_oauth_tokens_grant_id", "oauth_tokens", ["grant_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_tokens_grant_id", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_expires_at", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_oauth_grants_user_id", table_name="oauth_grants")
    op.drop_index("ix_oauth_grants_tenant_id", table_name="oauth_grants")
    op.drop_index("ix_oauth_grants_oauth_client_id", table_name="oauth_grants")
    op.drop_table("oauth_grants")
    op.drop_index("ix_oauth_codes_user_id", table_name="oauth_codes")
    op.drop_index("ix_oauth_codes_tenant_id", table_name="oauth_codes")
    op.drop_index("ix_oauth_codes_oauth_client_id", table_name="oauth_codes")
    op.drop_index("ix_oauth_codes_expires_at", table_name="oauth_codes")
    op.drop_table("oauth_codes")
    op.drop_table("oauth_clients")
