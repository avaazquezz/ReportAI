import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt used directly, not passlib — passlib's version-detection code breaks
# on bcrypt>=4.0 (it reads a `__about__` attribute that no longer exists).


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def _build_payload(data: dict[str, Any], expires_delta: timedelta) -> dict[str, Any]:
    now = datetime.now(UTC)
    payload = data.copy()
    payload["iat"] = now
    payload["exp"] = now + expires_delta
    payload["jti"] = str(uuid.uuid4())
    return payload


def create_access_token(data: dict[str, Any]) -> str:
    payload = _build_payload(data, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload["type"] = "access"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    payload = _build_payload(data, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload["type"] = "refresh"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
