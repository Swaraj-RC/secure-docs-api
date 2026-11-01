import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams
from app.db.models.document import DocClassification, DocStatus, Document
from app.db.models.user import User
from app.db.models.workspace import WorkspaceMember, WorkspaceRole
from app.policies.access import (
    can_create_document,
    can_edit_document,
    can_view_document,
    can_view_workspace,
    enforce_document_access,
)
from app.schemas.document import DocumentCreate, DocumentUpdate

ALLOWED_SORT_FIELDS = {
    "created_at": Document.created_at,
    "title": Document.title,
    "updated_at": Document.updated_at,
}


async def get_workspace_membership(
    db: AsyncSession,
    ws_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WorkspaceMember | None:
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == ws_id)
        .where(WorkspaceMember.user_id == user_id)
    )
    result = await db.scalars(stmt)
    return result.first()


async def create_document(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    payload: DocumentCreate,
) -> Document:
    member = await get_workspace_membership(db, ws_id, actor.id)
    if not member or not can_view_workspace(member.role):
        raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")

    if not can_create_document(member.role):
        raise ForbiddenError(
            "Insufficient permissions to create documents in this workspace",
            code="FORBIDDEN",
        )

    doc = Document(
        workspace_id=ws_id,
        title=payload.title,
        description=payload.description,
        classification=payload.classification,
        status=DocStatus.DRAFT,
        owner_id=actor.id,
        created_by=actor.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def get_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
) -> Document:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    can_view = can_view_document(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=None,
    )
    enforce_document_access(can_view, is_member, "view document")
    return doc


async def list_documents(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    pagination: PageParams,
    q: str | None = None,
    status: DocStatus | None = None,
    classification: DocClassification | None = None,
    owner_id: uuid.UUID | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    sort: str = "-created_at",
) -> Page[Document]:
    member = await get_workspace_membership(db, ws_id, actor.id)
    if not member or not can_view_workspace(member.role):
        raise NotFoundError("Workspace not found", code="WORKSPACE_NOT_FOUND")

    query = (
        select(Document).where(Document.workspace_id == ws_id).where(Document.deleted_at.is_(None))
    )

    if member.role in (WorkspaceRole.MEMBER, WorkspaceRole.VIEWER):
        query = query.where(
            or_(
                Document.classification.in_([DocClassification.PUBLIC, DocClassification.INTERNAL]),
                Document.owner_id == actor.id,
            )
        )

    if q:
        term = f"%{q}%"
        query = query.where(
            or_(
                Document.title.ilike(term),
                Document.description.ilike(term),
            )
        )

    if status:
        query = query.where(Document.status == status)

    if classification:
        query = query.where(Document.classification == classification)

    if owner_id:
        query = query.where(Document.owner_id == owner_id)

    if created_after:
        query = query.where(Document.created_at >= created_after)

    if created_before:
        query = query.where(Document.created_at <= created_before)

    sort_clean = sort.strip()
    descending = sort_clean.startswith("-")
    field_name = sort_clean[1:] if sort_clean.startswith(("+", "-")) else sort_clean

    if field_name not in ALLOWED_SORT_FIELDS:
        allowed = sorted(ALLOWED_SORT_FIELDS.keys())
        raise ValidationError(
            f"Invalid sort field '{field_name}'. Allowed fields: {allowed}",
            code="INVALID_SORT_FIELD",
        )

    col = ALLOWED_SORT_FIELDS[field_name]
    order_expr = col.desc() if descending else col.asc()
    query = query.order_by(order_expr)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = await db.scalar(count_query) or 0

    items_query = query.offset(pagination.offset).limit(pagination.size)
    items_result = await db.scalars(items_query)
    items = list(items_result.all())

    return Page.create(items=items, total=total, params=pagination)


async def update_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    payload: DocumentUpdate,
) -> Document:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    can_edit = can_edit_document(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=None,
    )
    enforce_document_access(can_edit, is_member, "edit document")

    updated = False
    if payload.title is not None:
        doc.title = payload.title
        updated = True
    if payload.description is not None:
        doc.description = payload.description
        updated = True
    if payload.status is not None:
        doc.status = payload.status
        updated = True
    if payload.classification is not None:
        doc.classification = payload.classification
        updated = True

    if updated:
        doc.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(doc)

    return doc


async def delete_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
) -> None:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    can_delete = bool(
        member
        and (doc.owner_id == actor.id or member.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN))
    )
    enforce_document_access(can_delete, is_member, "delete document")

    doc.deleted_at = datetime.now(UTC)
    await db.commit()


async def restore_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
) -> Document:
    stmt = select(Document).where(Document.id == doc_id)
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc or doc.deleted_at is None:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    can_restore = bool(member and member.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN))
    enforce_document_access(can_restore, is_member, "restore document")

    doc.deleted_at = None
    doc.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(doc)
    return doc
