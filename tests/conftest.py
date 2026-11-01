import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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


# SQLite dialect shims for PostgreSQL types when running tests without live PG
@compiles(CITEXT, "sqlite")
def _compile_citext_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "CHAR(36)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT"


@compiles(INET, "sqlite")
def _compile_inet_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "VARCHAR(45)"


TEST_DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(TEST_DB_URL, echo=False)
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
