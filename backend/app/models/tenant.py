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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
