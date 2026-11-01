"""Shared Pydantic schemas."""

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """A single field-level error detail."""

    field: str
    issue: str


class ErrorResponse(BaseModel):
    """Standard error response envelope (RFC 7807-ish)."""

    code: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str = ""


class ErrorEnvelope(BaseModel):
    """Wrapped error response."""

    error: ErrorResponse


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    environment: str


class ReadyResponse(BaseModel):
    """Readiness check response."""

    status: str
    checks: dict[str, Any] = {}
