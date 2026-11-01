"""Unit tests for Settings and environment validation."""

import pytest

from app.core.config import Settings, get_settings


def test_settings_defaults() -> None:
    """Test default settings."""
    settings = get_settings()
    assert settings.APP_NAME == "secure-docs-api"
    assert settings.ENVIRONMENT == "development"
    assert not settings.is_production
    assert settings.max_upload_size_bytes == 25 * 1024 * 1024
    assert "application/pdf" in settings.allowed_mime_types_list


def test_cors_origin_parsing() -> None:
    """Test parsing string and JSON CORS origins."""
    s1 = Settings.model_validate(
        {"BACKEND_CORS_ORIGINS": '["http://localhost:3000", "http://example.com"]'}
    )
    assert s1.BACKEND_CORS_ORIGINS == ["http://localhost:3000", "http://example.com"]

    s2 = Settings.model_validate(
        {"BACKEND_CORS_ORIGINS": "http://localhost:3000,http://example.com"}
    )
    assert s2.BACKEND_CORS_ORIGINS == ["http://localhost:3000", "http://example.com"]


def test_production_secret_key_validation() -> None:
    """Test that default SECRET_KEY fails fast in production."""
    with pytest.raises(ValueError, match="SECRET_KEY must be changed in production"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="CHANGE-ME-to-a-random-64-char-hex-string",
        )
