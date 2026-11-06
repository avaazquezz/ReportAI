from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RateLimitHit(Base):
    """One counted attempt (a failed sign-in, a reset email, a wrong setup code). Kept in Postgres
    so every API worker and every restart sees the same count. The worker deletes old rows."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (Index("ix_rate_limit_hits_key_at", "key", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
