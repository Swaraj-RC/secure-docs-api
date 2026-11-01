"""SQLAlchemy declarative base and shared mixins."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# SQLite shims for PostgreSQL-specific types during tests and local SQLite usage
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


class Base(DeclarativeBase):
    """Declarative base for all models."""

    pass


class UUIDMixin:
    """Mixin that adds a UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
