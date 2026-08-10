import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentType(Base):
    __tablename__ = "document_types"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_document_types_tenant_id_name"),
        Index("ix_document_types_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Exact shape defined by Phase 1's extraction work — Phase 0 just owns the column.
    field_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_emails: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
