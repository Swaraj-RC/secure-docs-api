import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ForbiddenError
from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_db as get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not auth or not auth.credentials:
        raise AuthenticationError("Authentication required", code="AUTHENTICATION_REQUIRED")

    payload = decode_access_token(auth.credentials)
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise AuthenticationError("Invalid token payload", code="AUTHENTICATION_REQUIRED")

    try:
        user_id = uuid.UUID(user_id_raw)
    except ValueError as e:
        raise AuthenticationError("Invalid token subject", code="AUTHENTICATION_REQUIRED") from e

    user = await db.get(User, user_id)
    if not user:
        raise AuthenticationError("User not found", code="AUTHENTICATION_REQUIRED")
    if not user.is_active:
        raise AuthenticationError("User is inactive", code="AUTHENTICATION_REQUIRED")

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise ForbiddenError("Superuser access required", code="FORBIDDEN")
    return current_user


__all__ = [
    "bearer_scheme",
    "get_current_active_superuser",
    "get_current_user",
    "get_db",
]
