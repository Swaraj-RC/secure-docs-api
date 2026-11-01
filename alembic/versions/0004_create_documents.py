"""create documents table and partial indexes

Revision ID: 0004_documents
Revises: 0003_workspaces
Create Date: 2026-11-01 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_documents"
down_revision: str | None = "0003_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    status_enum = postgresql.ENUM(
        "draft", "active", "archived", name="doc_status", create_type=True
    )
    status_enum.create(bind, checkfirst=True)

    classification_enum = postgresql.ENUM(
        "public", "internal", "confidential", "restricted",
        name="doc_classification",
        create_type=True,
    )
    classification_enum.create(bind, checkfirst=True)

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "active", "archived", name="doc_status", create_type=False
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "classification",
            postgresql.ENUM(
                "public",
                "internal",
                "confidential",
                "restricted",
                name="doc_classification",
                create_type=False,
            ),
            server_default="internal",
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"], unique=False)
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"], unique=False)
    op.create_index(
        "ix_documents_workspace_created",
        "documents",
        ["workspace_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_documents_workspace_status",
        "documents",
        ["workspace_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_documents_title_trgm ON documents USING gin (title gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_documents_title_trgm")

    op.drop_index("ix_documents_workspace_status", table_name="documents")
    op.drop_index("ix_documents_workspace_created", table_name="documents")
    op.drop_index("ix_documents_owner_id", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")

    classification_enum = postgresql.ENUM(
        "public", "internal", "confidential", "restricted",
        name="doc_classification",
        create_type=False,
    )
    classification_enum.drop(bind, checkfirst=True)

    status_enum = postgresql.ENUM(
        "draft", "active", "archived", name="doc_status", create_type=False
    )
    status_enum.drop(bind, checkfirst=True)
