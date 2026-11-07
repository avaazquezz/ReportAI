import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditEvent(Base):
    """Who did something security-relevant, to what, and when: a sign-in, a role change, a new
    API key. Written by services/audit.py in the transaction of the change it describes. Never
    holds a secret's value — only which fields changed. The worker deletes rows after a year."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_id_created_at", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # None for what concerns the platform rather than one company (the super admin's settings).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True
    )
    # The actor's email when it happened, so the record outlives the account; "system" or None
    # when nobody signed in did it.
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # dotted: auth.login_failed
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)  # the id it was done to
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
