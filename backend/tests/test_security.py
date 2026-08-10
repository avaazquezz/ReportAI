import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip() -> None:
    token = create_access_token({"sub": "user-123"})
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert "jti" in payload


def test_decode_token_rejects_tampered_token() -> None:
    token = create_access_token({"sub": "user-123"})
    # Flip a character in the middle of the signature, not the last one — base64url's
    # final character can land on padding-insensitive bits that don't always change the
    # decoded byte value, which made this test flaky depending on token length.
    middle = len(token) // 2
    flipped = "a" if token[middle] != "a" else "b"
    tampered = token[:middle] + flipped + token[middle + 1 :]
    with pytest.raises(ValueError):
        decode_token(tampered)
