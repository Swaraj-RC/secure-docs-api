import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_policy,
    verify_password,
)
from app.db.models.token import RefreshToken
from app.db.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse

settings = get_settings()

_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQxMjM0NTY3OA$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    validate_password_policy(payload.password)

    stmt = select(User).where(User.email == payload.email)
    existing = await db.scalar(stmt)
    if existing:
        raise ConflictError("Email already registered", code="CONFLICT")

    user = User(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    now = datetime.now(UTC)
    stmt = select(User).where(User.email == email)
    user = await db.scalar(stmt)

    if not user:
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationError("Invalid email or password", code="INVALID_CREDENTIALS")

    if user.locked_until and _to_utc(user.locked_until) > now:
        raise AuthenticationError(
            "Account locked due to too many failed attempts. Try again later.",
            code="ACCOUNT_LOCKED",
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
        await db.commit()
        raise AuthenticationError("Invalid email or password", code="INVALID_CREDENTIALS")

    if not user.is_active:
        raise AuthenticationError("Account is inactive", code="AUTHENTICATION_REQUIRED")

    user.failed_login_count = 0
    user.locked_until = None

    raw_token = generate_refresh_token()
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        family_id=uuid.uuid4(),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(token_record)
    await db.commit()

    access_token = create_access_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(raw_token)

    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    token_record = await db.scalar(stmt)

    if not token_record:
        raise AuthenticationError("Invalid refresh token", code="INVALID_REFRESH_TOKEN")

    # Reuse detection: an already-revoked token being presented means replay/theft
    if token_record.revoked_at is not None:
        revoke_family_stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == token_record.family_id)
            .where(RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.execute(revoke_family_stmt)
        await db.commit()
        raise AuthenticationError(
            "Refresh token reuse detected. Family revoked.",
            code="REFRESH_TOKEN_REUSED",
        )

    if _to_utc(token_record.expires_at) < now:
        raise AuthenticationError("Refresh token has expired", code="INVALID_REFRESH_TOKEN")

    user = await db.get(User, token_record.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User is inactive or deleted", code="AUTHENTICATION_REQUIRED")

    new_raw_token = generate_refresh_token()
    new_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_raw_token),
        family_id=token_record.family_id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(new_token_record)
    await db.flush()

    token_record.revoked_at = now
    token_record.replaced_by = new_token_record.id
    await db.commit()

    new_access_token = create_access_token(user.id)
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_raw_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(raw_token)
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(stmt)
    await db.commit()
