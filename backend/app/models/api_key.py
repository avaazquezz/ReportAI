import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiKey(Base):
    """A personal key a company user makes for an AI assistant (the MCP server): it acts as that
    person, with their role, and never more (services/api_keys.py). Only a hash of the secret is
    stored; the secret is shown once, when it is made."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # SHA-256 of the whole secret, hex. The secret has 256 random bits, so a fast hash is enough:
    # there is nothing to brute-force, and a slow one would cost every request.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # The secret's first characters, to tell keys apart in the panel ("rpt_Ab12…").
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # None: never expires (every key made before expiry existed, and those made that way on purpose).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
