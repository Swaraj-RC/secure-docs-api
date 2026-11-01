"""Application factory — creates, configures, and returns the FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import (
    generate_request_id,
    get_logger,
    request_id_ctx,
    setup_logging,
)
from app.core.rate_limit import limiter

logger = get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    logger.info("application_startup", environment=settings.ENVIRONMENT)
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    setup_logging(
        json_logs=settings.is_production,
        log_level="DEBUG" if settings.DEBUG else "INFO",
    )

    app = FastAPI(
        title=settings.APP_NAME,
        description="Secure Document & Records Management API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --- Rate limiter ---
    app.state.limiter = limiter

    # --- Middleware (order matters: outermost first) ---

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID + security headers middleware
    @app.middleware("http")
    async def request_middleware(request: Request, call_next: Any) -> Response:
        # Generate and set request ID
        rid = request.headers.get("X-Request-ID") or generate_request_id()
        request_id_ctx.set(rid)

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            from app.core.errors import _unhandled_error_handler

            response = await _unhandled_error_handler(request, exc)

        # Propagate request ID
        response.headers["X-Request-ID"] = rid

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "0"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response

    # --- Exception handlers ---
    register_exception_handlers(app)

    # --- Routers ---
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


# Module-level app instance for uvicorn
app = create_app()
