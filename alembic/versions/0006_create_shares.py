"""create document_shares table and share_permission enum

Revision ID: 0006_shares
Revises: 0005_versions
Create Date: 2026-11-01 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_shares"
down_revision: str | None = "0005_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    perm_enum = postgresql.ENUM(
        "read", "write", name="share_permission", create_type=True
    )
    perm_enum.create(bind, checkfirst=True)

    op.create_table(
        "document_shares",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "permission",
            postgresql.ENUM(
                "read", "write", name="share_permission", create_type=False
            ),
            server_default="read",
            nullable=False,
        ),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "user_id", name="uq_document_shares_doc_user"),
    )
    op.create_index("ix_document_shares_document_id", "document_shares", ["document_id"], unique=False)
    op.create_index("ix_document_shares_user_id", "document_shares", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_shares_user_id", table_name="document_shares")
    op.drop_index("ix_document_shares_document_id", table_name="document_shares")
    op.drop_table("document_shares")

    bind = op.get_bind()
    perm_enum = postgresql.ENUM(
        "read", "write", name="share_permission", create_type=False
    )
    perm_enum.drop(bind, checkfirst=True)
