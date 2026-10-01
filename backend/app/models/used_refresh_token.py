from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UsedRefreshToken(Base):
    """A refresh token that was already exchanged or logged out. Each one works once, so a copy
    someone stole stops working at its owner's next refresh. Rows are useless once the token
    would have expired anyway, and the worker deletes them."""

    __tablename__ = "used_refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
