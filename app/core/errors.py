"""Application error hierarchy and FastAPI exception handlers.

All errors follow an RFC 7807-inspired envelope:
{
    "error": {
        "code": "STABLE_UPPER_SNAKE_CODE",
        "message": "human readable description",
        "details": [{"field": "...", "issue": "..."}],
        "request_id": "uuid"
    }
}
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, get_request_id

logger = get_logger()


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found (or hidden for leakage prevention)."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class AuthenticationError(AppError):
    """Authentication failure (401)."""

    def __init__(
        self,
        message: str = "Could not validate credentials",
        code: str = "AUTHENTICATION_REQUIRED",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenError(AppError):
    """Permission denied (403)."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        code: str = "FORBIDDEN",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictError(AppError):
    """Resource conflict (409)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "CONFLICT",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class RateLimitError(AppError):
    """Too many requests (429)."""

    def __init__(
        self,
        message: str = "Too many requests, please try again later",
        code: str = "RATE_LIMITED",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class RangeNotSatisfiableError(AppError):
    """Range request cannot be satisfied (416)."""

    def __init__(
        self,
        message: str = "Requested range not satisfiable",
        code: str = "RANGE_NOT_SATISFIABLE",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            details=details,
        )


class ValidationError(AppError):
    """Business-logic validation error (422)."""

    def __init__(
        self,
        message: str = "Validation error",
        code: str = "VALIDATION_ERROR",
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


def _build_error_body(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a standard error response body."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": get_request_id(),
        }
    }


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle AppError subclasses."""
    logger.warning(
        "app_error",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=str(request.url.path),
    )
    headers: dict[str, str] = {}
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(exc.code, exc.message, exc.details),
        headers=headers if headers else None,
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors -> 422 with field details."""
    details = [
        {
            "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
            "issue": err.get("msg", "Invalid value"),
        }
        for err in exc.errors()
    ]
    logger.warning(
        "validation_error",
        path=str(request.url.path),
        detail_count=len(details),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_body("VALIDATION_ERROR", "Request validation failed", details),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — never leak internals."""
    logger.exception(
        "unhandled_error",
        path=str(request.url.path),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_body(
            "INTERNAL_ERROR",
            "An unexpected error occurred. Reference request_id when contacting support.",
        ),
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions (404, 405, etc.) with RFC 7807 envelope."""
    status_to_code = {
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    }
    code = status_to_code.get(exc.status_code, "HTTP_ERROR")
    logger.warning(
        "http_exception",
        path=str(request.url.path),
        status_code=exc.status_code,
        detail=str(exc.detail),
    )
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_body(code, str(exc.detail)),
        headers=headers,
    )


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle rate limit exceedances with RFC 7807 envelope and Retry-After header."""
    logger.warning("rate_limit_exceeded", path=str(request.url.path), detail=str(exc.detail))
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=_build_error_body("RATE_LIMIT_EXCEEDED", f"Rate limit exceeded: {exc.detail}"),
    )
    response.headers["Retry-After"] = "60"
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
