import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_execution_logs_tenant_id", "tenant_id"),
        Index("ix_execution_logs_tenant_id_created_at", "tenant_id", "created_at"),
        # The platform's spend breaker sums today's platform-paid cost on every message.
        Index("ix_execution_logs_platform_created_at", "created_at", postgresql_where=text("platform_key")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Who paid for the call: the platform's keys (true), or the company's own (false). Defaults to
    # the platform, so a call nobody labelled counts against the platform's breaker, not past it.
    platform_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
