import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.document import Document
from app.db.models.share import DocumentShare
from app.db.models.user import User
from app.db.models.workspace import WorkspaceMember
from app.policies.access import (
    can_grant_share,
    can_manage_shares,
    enforce_document_access,
    is_share_active,
)
from app.schemas.share import ShareCreate


async def get_active_share(
    db: AsyncSession,
    doc_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DocumentShare | None:
    stmt = (
        select(DocumentShare)
        .where(DocumentShare.document_id == doc_id)
        .where(DocumentShare.user_id == user_id)
    )
    result = await db.scalars(stmt)
    share = result.first()
    if not share:
        return None
    if not is_share_active(share):
        return None
    return share


async def grant_share(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    payload: ShareCreate,
) -> DocumentShare:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    mem_stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == doc.workspace_id)
        .where(WorkspaceMember.user_id == actor.id)
    )
    mem_res = await db.scalars(mem_stmt)
    member = mem_res.first()
    is_member = member is not None

    granter_role = member.role if member else None
    granter_is_owner = doc.owner_id == actor.id

    if not is_member and not granter_is_owner:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    if not can_grant_share(granter_role, granter_is_owner, payload.permission):
        raise ForbiddenError(
            f"Cannot grant '{payload.permission}' permission on this document",
            code="FORBIDDEN",
        )

    # Resolve target user by ID or email
    target_user: User | None = None
    if payload.user_id:
        target_user = await db.get(User, payload.user_id)
    elif payload.email:
        user_stmt = select(User).where(User.email == payload.email)
        user_res = await db.scalars(user_stmt)
        target_user = user_res.first()

    if not target_user:
        raise NotFoundError("Target user not found", code="USER_NOT_FOUND")

    # Upsert share
    share_stmt = (
        select(DocumentShare)
        .where(DocumentShare.document_id == doc_id)
        .where(DocumentShare.user_id == target_user.id)
    )
    existing_share = (await db.scalars(share_stmt)).first()

    if existing_share:
        existing_share.permission = payload.permission
        existing_share.expires_at = payload.expires_at
        existing_share.granted_by = actor.id
        share = existing_share
    else:
        share = DocumentShare(
            document_id=doc_id,
            user_id=target_user.id,
            permission=payload.permission,
            granted_by=actor.id,
            expires_at=payload.expires_at,
        )
        db.add(share)

    doc.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(share)
    return share


async def list_shares(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
) -> list[DocumentShare]:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    mem_stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == doc.workspace_id)
        .where(WorkspaceMember.user_id == actor.id)
    )
    member = (await db.scalars(mem_stmt)).first()
    is_member = member is not None

    can_manage = can_manage_shares(actor.id, doc, member.role if member else None)
    enforce_document_access(can_manage, is_member, "list document shares")

    # Exclude expired shares at query time
    now = datetime.now(UTC)
    shares_stmt = (
        select(DocumentShare)
        .where(DocumentShare.document_id == doc_id)
        .where(or_(DocumentShare.expires_at.is_(None), DocumentShare.expires_at > now))
        .order_by(DocumentShare.created_at.desc())
    )
    shares_result = await db.scalars(shares_stmt)
    return list(shares_result.all())


async def revoke_share(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    share_id: uuid.UUID,
) -> None:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    mem_stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == doc.workspace_id)
        .where(WorkspaceMember.user_id == actor.id)
    )
    member = (await db.scalars(mem_stmt)).first()
    is_member = member is not None

    can_manage = can_manage_shares(actor.id, doc, member.role if member else None)
    enforce_document_access(can_manage, is_member, "revoke document share")

    share_stmt = (
        select(DocumentShare)
        .where(DocumentShare.id == share_id)
        .where(DocumentShare.document_id == doc_id)
    )
    share = (await db.scalars(share_stmt)).first()
    if not share:
        raise NotFoundError("Share not found", code="SHARE_NOT_FOUND")

    await db.delete(share)
    doc.updated_at = datetime.now(UTC)
    await db.commit()
