"""Unit tests for error envelope and custom exceptions."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core.errors import (
    AuthenticationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from app.main import create_app


def test_app_error_hierarchy() -> None:
    """Verify error status codes and default codes."""
    assert NotFoundError().status_code == 404
    assert NotFoundError().code == "NOT_FOUND"

    assert AuthenticationError().status_code == 401
    assert AuthenticationError().code == "AUTHENTICATION_REQUIRED"

    assert ForbiddenError().status_code == 403
    assert ForbiddenError().code == "FORBIDDEN"

    assert ConflictError().status_code == 409
    assert ConflictError().code == "CONFLICT"

    assert RateLimitError().status_code == 429
    assert RateLimitError().code == "RATE_LIMITED"

    assert ValidationError().status_code == 422
    assert ValidationError().code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_404_error_envelope() -> None:
    """Verify 404 handler returns RFC 7807 envelope."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/nonexistent-route")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_custom_exception_handlers() -> None:
    """Verify AppError and unhandled exception handlers."""
    test_router = APIRouter()

    @test_router.get("/trigger-auth-error")
    async def trigger_auth() -> None:
        raise AuthenticationError("Custom auth error message")

    @test_router.get("/trigger-server-error")
    async def trigger_server_error() -> None:
        raise RuntimeError("Something exploded")

    app = create_app()
    app.include_router(test_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 401
        res_auth = await client.get("/trigger-auth-error")
        assert res_auth.status_code == 401
        assert res_auth.headers.get("WWW-Authenticate") == "Bearer"
        assert res_auth.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

        # 500
        res_500 = await client.get("/trigger-server-error")
        assert res_500.status_code == 500
        assert res_500.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "request_id" in res_500.json()["error"]
