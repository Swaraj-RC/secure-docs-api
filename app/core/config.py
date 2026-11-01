from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # Application
    APP_NAME: str = "secure-docs-api"
    ENVIRONMENT: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "SECURE_DOCS_ENV"),
    )
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    HOST: str = "0.0.0.0"  # noqa: S104
    PORT: int = 8000
    WORKERS: int = 1

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://securedocs:securedocs_dev@localhost:5432/securedocs",
        validation_alias=AliasChoices("DATABASE_URL", "SECURE_DOCS_DB_URL"),
    )
    DATABASE_ECHO: bool = False

    # Auth / JWT
    SECRET_KEY: str = Field(
        default="CHANGE-ME-to-a-random-64-char-hex-string",
        validation_alias=AliasChoices("SECRET_KEY", "SECURE_DOCS_JWT_SECRET"),
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Passwords
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # Storage
    STORAGE_BACKEND: str = Field(
        default="local",
        validation_alias=AliasChoices("STORAGE_BACKEND", "SECURE_DOCS_STORAGE_BACKEND"),
    )
    LOCAL_STORAGE_PATH: str = Field(
        default="./uploads",
        validation_alias=AliasChoices("LOCAL_STORAGE_PATH", "SECURE_DOCS_STORAGE_PATH"),
    )
    S3_BUCKET_NAME: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_ENDPOINT_URL: str = ""

    # File uploads
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_MIME_TYPES: str = (
        "application/pdf,image/png,image/jpeg,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "text/plain,text/csv"
    )

    # Rate limiting
    RATE_LIMITING_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    @property
    def max_upload_size_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def allowed_mime_types_list(self) -> list[str]:
        """Parsed list of allowed MIME types."""
        return [t.strip() for t in self.ALLOWED_MIME_TYPES.split(",") if t.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Fail fast if production is missing real secrets."""
        if self.is_production and self.SECRET_KEY == "CHANGE-ME-to-a-random-64-char-hex-string":
            raise ValueError("SECRET_KEY must be changed in production")
        return self

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json

            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except (json.JSONDecodeError, TypeError):
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v) if isinstance(v, (list, set)) else [str(v)]


@lru_cache
def get_settings() -> Settings:
    """Create and return cached settings instance."""
    return Settings()


settings: Settings = get_settings()
