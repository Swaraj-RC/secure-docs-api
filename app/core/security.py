import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ValidationError

settings = get_settings()

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_password_policy(password: str) -> None:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValidationError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long",
            code="PASSWORD_TOO_WEAK",
            details=[{"field": "password", "issue": "Minimum length requirement not met"}],
        )


def create_access_token(
    subject: str | uuid.UUID,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + delta

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return cast(str, encoded)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationError("Token has expired", code="TOKEN_EXPIRED") from e
    except JWTError as e:
        raise AuthenticationError(
            "Could not validate credentials", code="AUTHENTICATION_REQUIRED"
        ) from e


def generate_refresh_token() -> str:
    return secrets.token_hex(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
