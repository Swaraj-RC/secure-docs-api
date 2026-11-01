"""Unit tests for database session setup."""

from app.db.session import async_session_factory, engine


def test_session_engine_configuration() -> None:
    """Verify engine and session maker configuration."""
    assert engine is not None
    assert async_session_factory is not None
