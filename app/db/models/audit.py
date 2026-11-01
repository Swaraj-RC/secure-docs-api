from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, UUIDMixin


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45).with_variant(INET(), "postgresql"),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    actor = relationship("User", lazy="selectin")
    workspace = relationship("Workspace", lazy="selectin")

    __table_args__ = (
        Index("ix_audit_workspace_created", "workspace_id", created_at.desc()),
        Index("ix_audit_actor", "actor_id", created_at.desc()),
        Index("ix_audit_resource", "resource_type", "resource_id"),
    )
