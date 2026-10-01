import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_tenant_id", "tenant_id"),
        # A sender has at most one report in flight or waiting on them.
        Index(
            "uq_reports_one_active_per_sender",
            "tenant_id",
            "requester_channel",
            "requester_identifier",
            unique=True,
            postgresql_where=text(
                "status IN ('pending', 'awaiting_doctype_selection', 'awaiting_details', 'awaiting_approval')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL, not CASCADE — deleting a document type shouldn't erase report history.
    document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True
    )
    # 30, not 20: "awaiting_doctype_selection" is 26 chars (migration 0007)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    requester_channel: Mapped[str] = mapped_column(String(50), nullable=False)
    requester_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # What the panel shows for review: the text the fields were extracted from (a
    # transcript for voice notes), the audio, the fields and the quote backing each one.
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extracted_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channel_connections.id", ondelete="SET NULL"), nullable=True
    )
    channel_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bumped by every status change, including a paused report being claimed for resume —
    # the stuck-report sweep measures inactivity from here.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
