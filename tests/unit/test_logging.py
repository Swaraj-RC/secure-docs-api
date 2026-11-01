"""Unit tests for structured logging and request ID context."""

from app.core.logging import (
    add_request_id,
    generate_request_id,
    get_logger,
    get_request_id,
    request_id_ctx,
    setup_logging,
)


def test_request_id_generation() -> None:
    """Test generating a unique request ID."""
    rid1 = generate_request_id()
    rid2 = generate_request_id()
    assert rid1 != rid2
    assert len(rid1) == 36


def test_add_request_id_processor() -> None:
    """Test injecting request ID into log event dict."""
    request_id_ctx.set("test-rid-1234")
    assert get_request_id() == "test-rid-1234"

    event_dict: dict[str, str] = {"event": "test"}
    result = add_request_id(None, "info", event_dict)
    assert result["request_id"] == "test-rid-1234"


def test_setup_logging_json() -> None:
    """Test configuring logging for json and console formats."""
    setup_logging(json_logs=True, log_level="DEBUG")
    setup_logging(json_logs=False, log_level="INFO")
    logger = get_logger()
    assert logger is not None

