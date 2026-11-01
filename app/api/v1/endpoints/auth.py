from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import (
    authenticate_user,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await register_user(db, payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain tokens",
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = request.client.host if request.client else None
    agent = request.headers.get("User-Agent")
    return await authenticate_user(
        db=db,
        email=str(payload.email),
        password=payload.password,
        ip_address=ip,
        user_agent=agent,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token for a new token pair",
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh_token_endpoint(
    payload: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    ip = request.client.host if request.client else None
    agent = request.headers.get("User-Agent")
    return await rotate_refresh_token(
        db=db,
        raw_token=payload.refresh_token,
        ip_address=ip,
        user_agent=agent,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke refresh token",
)
async def logout(
    payload: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await revoke_refresh_token(db=db, raw_token=payload.refresh_token)
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
