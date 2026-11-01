"""create audit_logs table

Revision ID: 0007_audit
Revises: 0006_shares
Create Date: 2026-11-01 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_audit"
down_revision: str | None = "0006_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ip_address",
            postgresql.INET() if is_pg else sa.String(length=45),
            nullable=True,
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB() if is_pg else sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_workspace_created",
        "audit_logs",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_actor",
        "audit_logs",
        ["actor_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_resource", table_name="audit_logs")
    op.drop_index("ix_audit_actor", table_name="audit_logs")
    op.drop_index("ix_audit_workspace_created", table_name="audit_logs")
    op.drop_table("audit_logs")

