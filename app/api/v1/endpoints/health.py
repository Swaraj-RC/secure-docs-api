"""Health and readiness check endpoints."""

from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import HealthResponse, ReadyResponse

router = APIRouter()
settings = get_settings()


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 if the service is running.",
)
async def healthz() -> HealthResponse:
    """Liveness check — always returns OK if the process is up."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        environment=settings.ENVIRONMENT,
    )


@router.get(
    "/readyz",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description="Returns 200 if the service and its dependencies are ready.",
)
async def readyz() -> ReadyResponse:
    """Readiness check — verifies DB and storage connectivity.

    TODO (Day 2+): Actually check DB and storage backend.
    """
    checks: dict[str, Any] = {
        "database": "ok",
        "storage": "ok",
    }
    return ReadyResponse(
        status="ready",
        checks=checks,
    )
