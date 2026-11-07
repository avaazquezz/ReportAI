"""Secrets kept in the database — channel tokens, the AI and SMTP keys entered in the panel — are
encrypted with a key that lives only in the server's environment, so a stolen database dump or
backup does not hand over the company's credentials.

The key is derived from ENCRYPTION_KEY, or from SECRET_KEY when an older installation has no
ENCRYPTION_KEY yet. Changing it makes every stored secret unreadable: they have to be entered again."""

import base64
import json
from datetime import timedelta
from functools import cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


class UndecryptableSecretError(RuntimeError):
    """A stored secret no longer opens with this server's key."""


@cache
def _fernet(info: bytes = b"reportai secrets at rest") -> Fernet:
    material = (settings.ENCRYPTION_KEY or settings.SECRET_KEY).encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(material)
    return Fernet(base64.urlsafe_b64encode(key))


# Its own key: a link's token never opens a stored secret, nor the other way round.
_LINKS = b"reportai sealed links"


def seal(payload: dict[str, Any]) -> str:
    """The payload as a token only this server can read back, for a link sent by email: nothing in
    it is readable in a URL or a log, it can't be altered, and it carries when it was made."""
    return _fernet(_LINKS).encrypt(json.dumps(payload).encode()).decode()


def unseal(token: str, max_age: timedelta) -> dict[str, Any]:
    """Raises ValueError for a token this server didn't make, an altered one, or one older than max_age."""
    try:
        payload: dict[str, Any] = json.loads(_fernet(_LINKS).decrypt(token.encode(), ttl=int(max_age.total_seconds())))
    except InvalidToken as exc:
        raise ValueError("The link is wrong or has expired") from exc
    return payload


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise UndecryptableSecretError(
            "A stored secret can't be decrypted: ENCRYPTION_KEY (or SECRET_KEY) changed since it was saved. "
            "Enter that secret again in the panel."
        ) from exc


class EncryptedJSON(TypeDecorator[dict[str, Any]]):
    """A dict stored as one encrypted string: unreadable in the database, a dict in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: dict[str, Any] | None, dialect: Dialect) -> str | None:
        return None if value is None else encrypt(json.dumps(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> dict[str, Any] | None:
        return None if value is None else json.loads(decrypt(value))
