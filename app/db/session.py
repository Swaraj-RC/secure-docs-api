"""Async database engine and session management."""

import socket
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger()
settings = get_settings()


def _get_effective_db_url() -> str:
    url = settings.DATABASE_URL
    if not settings.is_production and ("localhost:5432" in url or "127.0.0.1:5432" in url):
        try:
            with socket.create_connection(("127.0.0.1", 5432), timeout=0.2):
                return url
        except (OSError, TimeoutError):
            logger.warning(
                "PostgreSQL at localhost:5432 is unreachable; "
                "falling back to SQLite for local development."
            )
            return "sqlite+aiosqlite:///./securedocs.db"
    return url


db_url = _get_effective_db_url()

engine_kwargs: dict[str, Any] = {
    "echo": settings.DATABASE_ECHO,
}
if not db_url.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        }
    )

engine = create_async_engine(
    db_url,
    **engine_kwargs,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
