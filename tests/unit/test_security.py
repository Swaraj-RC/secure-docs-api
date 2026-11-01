from datetime import timedelta

import pytest

from app.core.errors import AuthenticationError, ValidationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_policy,
    verify_password,
)


def test_argon2_hash_and_verify() -> None:
    raw = "Stron9#Passw0rd_2026!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_password_policy() -> None:
    with pytest.raises(ValidationError) as exc_info:
        validate_password_policy("short")
    assert exc_info.value.code == "PASSWORD_TOO_WEAK"

    # Should not raise for valid length
    validate_password_policy("12345678")


def test_jwt_access_token_roundtrip() -> None:
    subject = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(subject, expires_delta=timedelta(minutes=5))
    claims = decode_access_token(token)

    assert claims["sub"] == subject
    assert "jti" in claims
    assert "iat" in claims
    assert "exp" in claims


def test_jwt_tampered_token() -> None:
    subject = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(subject)
    tampered = token[:-4] + "abcd"

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(tampered)
    assert exc_info.value.code == "AUTHENTICATION_REQUIRED"


def test_jwt_expired_token() -> None:
    subject = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(subject, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(token)
    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_refresh_token_hashing() -> None:
    token1 = generate_refresh_token()
    token2 = generate_refresh_token()
    assert token1 != token2
    assert len(token1) == 64

    hash1 = hash_refresh_token(token1)
    hash2 = hash_refresh_token(token1)
    assert hash1 == hash2
    assert len(hash1) == 64

