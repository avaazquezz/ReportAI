"""The rows behind OAuth sign-in for AI assistants (services/oauth/): the apps that may ask, the
one-use codes a consent hands out, the grants a person gave, and the tokens each grant holds. Codes
and tokens are kept only as SHA-256 hashes: each has 256 random bits, so a fast hash is enough."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OAuthClient(Base):
    """An app that may ask a person for access: one that registered itself (DCR, `kind` dcr), or
    one known by the URL of its published metadata document (CIMD, `kind` cimd), cached here."""

    __tablename__ = "oauth_clients"
    __table_args__ = (CheckConstraint("kind IN ('dcr', 'cimd')", name="ck_oauth_clients_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # What the app sends as client_id: a UUID this server issued (dcr), or its document's https URL.
    client_id: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    # Its RFC 7591 metadata (redirect URIs, name, grant types...), without the secret.
    client_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    # A registered app's secret, if it asked for one, encrypted (app.core.crypto.encrypt).
    client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # When its document was last fetched (cimd); refetched once it is a day old.
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A code exchanged or a token refreshed: an app unused for long is purged (data_lifecycle).
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthCode(Base):
    """What a person's consent hands the app, for one exchange within minutes: bound to the app,
    the person, the redirect URI and the PKCE challenge it was asked with."""

    __tablename__ = "oauth_codes"
    __table_args__ = (Index("ix_oauth_codes_expires_at", "expires_at"),)

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    oauth_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("oauth_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    # Whether the app named the redirect URI itself: then the token request must name it too.
    redirect_uri_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthGrant(Base):
    """A person's consent to one app: what the panel lists as a connected app and what revoking
    ends, with every token it holds. It acts as that person, with their role, and never more."""

    __tablename__ = "oauth_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    oauth_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("oauth_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(200), nullable=False)
    # The MCP server its tokens are for (RFC 8707): /mcp takes them only if it is this server.
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthToken(Base):
    """An access token (an hour) or a refresh token (30 days) of a grant. A refresh token works
    once: `used_at` marks it spent, and presenting it again revokes the whole grant."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        CheckConstraint("kind IN ('access', 'refresh')", name="ck_oauth_tokens_kind"),
        Index("ix_oauth_tokens_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("oauth_grants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
