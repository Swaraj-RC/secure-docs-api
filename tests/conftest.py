import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

from app.api.deps import get_db
from app.core.rate_limit import limiter
from app.db.base import Base
from app.main import create_app


# SQLite dialect shims for PostgreSQL types when running tests with TEST_BACKEND=sqlite
@compiles(CITEXT, "sqlite")
def _compile_citext_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT COLLATE NOCASE"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "CHAR(36)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT"


@compiles(INET, "sqlite")
def _compile_inet_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "VARCHAR(45)"


TEST_BACKEND = os.environ.get("TEST_BACKEND", "").lower()
db_env = os.environ.get("SECURE_DOCS_TEST_DB_URL") or os.environ.get("DATABASE_URL", "")
USE_SQLITE = (
    TEST_BACKEND == "sqlite"
    or db_env.startswith("sqlite")
    or (not db_env and TEST_BACKEND != "postgres")
)

if USE_SQLITE:
    TEST_DB_URL = db_env if db_env.startswith("sqlite") else "sqlite+aiosqlite:///:memory:"
    IS_POSTGRES = False
else:
    # PostgreSQL is the default test backend
    TEST_DB_URL = (
        os.environ.get("SECURE_DOCS_TEST_DB_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://test:test@localhost:5432/test"
    )
    IS_POSTGRES = True


_MIGRATIONS_INITIALIZED = False


def _apply_alembic_migrations(db_url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    global _MIGRATIONS_INITIALIZED
    engine = create_async_engine(TEST_DB_URL, echo=False)

    if IS_POSTGRES:
        if not _MIGRATIONS_INITIALIZED:
            _apply_alembic_migrations(TEST_DB_URL)
            _MIGRATIONS_INITIALIZED = True
        yield engine
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE TABLE audit_logs, document_shares, document_versions, "
                    "documents, workspace_members, workspaces, refresh_tokens, users "
                    "RESTART IDENTITY CASCADE"
                )
            )
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    limiter.reset()
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
