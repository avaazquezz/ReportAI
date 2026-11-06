import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # What the bot speaks to this company's people, and the clock "tomorrow" is resolved against.
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="es", server_default="es")
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Europe/Madrid", server_default="Europe/Madrid"
    )
    # The company's look on what it sends: emails and, through {{ branding.* }}, its documents.
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # #RRGGBB
    logo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Its emails leave from the platform's address; replies to them go here, to the company.
    reply_to_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # What it may use (services/plans.py). Defaults keep companies from before plans unlimited.
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="unlimited", server_default="unlimited")
    plan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    plan_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Its admin asked to delete it: blocked since, purged with all its data after a grace period
    # (services/data_lifecycle.py). Reactivating the company cancels the request.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
