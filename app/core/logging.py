"""Structured logging configuration with request_id propagation."""

import contextvars
import logging
import uuid
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

# Context variable for request tracing
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get()


def generate_request_id() -> str:
    """Generate a new unique request ID."""
    return str(uuid.uuid4())


def add_request_id(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor to inject request_id into every log entry."""
    rid = request_id_ctx.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def setup_logging(*, json_logs: bool = False, log_level: str = "INFO") -> None:
    """Configure structlog for the application.

    Args:
        json_logs: Use JSON output (for production). Console output otherwise.
        log_level: Minimum log level.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(**kwargs))
