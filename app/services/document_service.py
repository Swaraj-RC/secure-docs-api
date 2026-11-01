import contextlib
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams
from app.db.models.document import DocClassification, DocStatus, Document
from app.db.models.user import User
from app.db.models.version import DocumentVersion
from app.db.models.workspace import WorkspaceMember, WorkspaceRole
from app.policies.access import (
    can_create_document,
    can_download_document,
    can_edit_document,
    can_upload_version,
    can_view_document,
    can_view_workspace,
    enforce_document_access,
    is_share_active,
)
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.audit_service import record_audit_event
from app.services.file_validation import process_streaming_upload
from app.services.share_service import get_active_share
from app.storage.base import StorageBackend

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
    ip_address: str | None = None,
    user_agent: str | None = None,
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
    await db.flush()

    classification_str = (
        doc.classification.value if hasattr(doc.classification, "value") else doc.classification
    )
    await record_audit_event(
        db,
        workspace_id=ws_id,
        actor_id=actor.id,
        action="doc.create",
        resource_type="document",
        resource_id=doc.id,
        metadata={"title": doc.title, "classification": str(classification_str)},
        ip_address=ip_address,
        user_agent=user_agent,
    )

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
    share = await get_active_share(db, doc.id, actor.id)
    is_authorized = is_member or (share is not None and is_share_active(share))

    can_view = can_view_document(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=share,
    )
    enforce_document_access(can_view, is_authorized, "view document")
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

    query = select(Document).where(
        Document.workspace_id == ws_id,
        Document.deleted_at.is_(None),
    )

    # Classification & status visibility filtering
    if member.role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        pass
    else:
        # Regular members/viewers can only see public/internal documents or documents they own
        query = query.where(
            or_(
                Document.owner_id == actor.id,
                Document.classification.in_([DocClassification.PUBLIC, DocClassification.INTERNAL]),
            )
        )
        query = query.where(
            or_(
                Document.owner_id == actor.id,
                Document.status != DocStatus.ARCHIVED,
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
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Document:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    share = await get_active_share(db, doc.id, actor.id)
    is_authorized = is_member or (share is not None and is_share_active(share))

    can_edit = can_edit_document(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=share,
    )
    enforce_document_access(can_edit, is_authorized, "edit document")

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
        await record_audit_event(
            db,
            workspace_id=doc.workspace_id,
            actor_id=actor.id,
            action="doc.update",
            resource_type="document",
            resource_id=doc.id,
            metadata={"updates": payload.model_dump(exclude_unset=True, mode="json")},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        await db.refresh(doc)

    return doc


async def delete_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
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
    await record_audit_event(
        db,
        workspace_id=doc.workspace_id,
        actor_id=actor.id,
        action="doc.delete",
        resource_type="document",
        resource_id=doc.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()


async def restore_document(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
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
    await record_audit_event(
        db,
        workspace_id=doc.workspace_id,
        actor_id=actor.id,
        action="doc.restore",
        resource_type="document",
        resource_id=doc.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(doc)
    return doc


async def upload_document_version(
    db: AsyncSession,
    storage: StorageBackend,
    actor: User,
    doc_id: uuid.UUID,
    file: UploadFile,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentVersion:
    stmt = select(Document).where(Document.id == doc_id).where(Document.deleted_at.is_(None))
    result = await db.scalars(stmt)
    doc = result.first()
    if not doc:
        raise NotFoundError("Document not found", code="DOCUMENT_NOT_FOUND")

    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    share = await get_active_share(db, doc.id, actor.id)
    is_authorized = is_member or (share is not None and is_share_active(share))

    can_upload = can_upload_version(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=share,
    )
    enforce_document_access(can_upload, is_authorized, "upload version to document")

    validated = await process_streaming_upload(file)

    async def _file_stream() -> AsyncIterator[bytes]:
        with open(validated.temp_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    storage_saved = False
    try:
        await storage.put(validated.storage_key, _file_stream())
        storage_saved = True

        ver_stmt = select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
            DocumentVersion.document_id == doc_id
        )
        max_ver = await db.scalar(ver_stmt) or 0
        next_ver = max_ver + 1

        version = DocumentVersion(
            document_id=doc_id,
            version_number=next_ver,
            storage_key=validated.storage_key,
            original_filename=validated.original_filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            checksum_sha256=validated.checksum_sha256,
            uploaded_by=actor.id,
        )
        db.add(version)
        await db.flush()

        doc.current_version_id = version.id
        doc.updated_at = datetime.now(UTC)

        await record_audit_event(
            db,
            workspace_id=doc.workspace_id,
            actor_id=actor.id,
            action="doc.version_create",
            resource_type="document_version",
            resource_id=version.id,
            metadata={
                "version_number": version.version_number,
                "size_bytes": version.size_bytes,
                "mime_type": version.mime_type,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await db.commit()
        await db.refresh(version)
        return version
    except Exception:
        if storage_saved:
            await storage.delete(validated.storage_key)
        raise
    finally:
        if validated.temp_path.exists():
            with contextlib.suppress(OSError):
                os.remove(validated.temp_path)


async def list_document_versions(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
) -> list[DocumentVersion]:
    doc = await get_document(db=db, actor=actor, doc_id=doc_id)
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
    )
    result = await db.scalars(stmt)
    return list(result.all())


async def get_document_version_for_download(
    db: AsyncSession,
    actor: User,
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[Document, DocumentVersion]:
    doc = await get_document(db=db, actor=actor, doc_id=doc_id)
    member = await get_workspace_membership(db, doc.workspace_id, actor.id)
    is_member = member is not None
    share = await get_active_share(db, doc.id, actor.id)
    is_authorized = is_member or (share is not None and is_share_active(share))

    can_dl = can_download_document(
        actor_id=actor.id,
        doc=doc,
        role=member.role if member else None,
        share=share,
    )
    enforce_document_access(can_dl, is_authorized, "download document")

    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.id == version_id)
        .where(DocumentVersion.document_id == doc_id)
    )
    result = await db.scalars(stmt)
    version = result.first()
    if not version:
        raise NotFoundError("Version not found", code="VERSION_NOT_FOUND")

    await record_audit_event(
        db,
        workspace_id=doc.workspace_id,
        actor_id=actor.id,
        action="doc.download",
        resource_type="document_version",
        resource_id=version.id,
        metadata={"version_number": version.version_number},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()

    return doc, version
