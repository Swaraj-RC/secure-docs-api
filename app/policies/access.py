import uuid
from datetime import UTC, datetime
from typing import Protocol

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.workspace import WorkspaceRole


class DocumentAccessProtocol(Protocol):
    @property
    def owner_id(self) -> uuid.UUID: ...

    @property
    def classification(self) -> str: ...

    @property
    def status(self) -> str: ...


class ShareAccessProtocol(Protocol):
    @property
    def user_id(self) -> uuid.UUID: ...

    @property
    def permission(self) -> str: ...

    @property
    def expires_at(self) -> datetime | None: ...


def can_view_workspace(role: WorkspaceRole | None) -> bool:
    return role is not None


def can_manage_workspace(role: WorkspaceRole | None) -> bool:
    return role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)


def can_delete_workspace(role: WorkspaceRole | None) -> bool:
    return role == WorkspaceRole.OWNER


def can_manage_members(role: WorkspaceRole | None) -> bool:
    return role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)


def can_create_document(role: WorkspaceRole | None) -> bool:
    return role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER)


def is_share_active(share: ShareAccessProtocol | None, now: datetime | None = None) -> bool:
    if not share:
        return False
    if share.expires_at is None:
        return True
    current = now or datetime.now(UTC)
    expiry = (
        share.expires_at.replace(tzinfo=UTC)
        if share.expires_at.tzinfo is None
        else share.expires_at
    )
    return expiry > current


def can_view_document(
    actor_id: uuid.UUID,
    doc: DocumentAccessProtocol,
    role: WorkspaceRole | None,
    share: ShareAccessProtocol | None = None,
    now: datetime | None = None,
) -> bool:
    # Non-member with no active share has zero access
    if role is None and not is_share_active(share, now):
        return False

    if doc.owner_id == actor_id:
        return True

    if role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        return True

    if is_share_active(share, now):
        return True

    if role in (WorkspaceRole.MEMBER, WorkspaceRole.VIEWER):
        return doc.classification in ("public", "internal")

    return False


def can_edit_document(
    actor_id: uuid.UUID,
    doc: DocumentAccessProtocol,
    role: WorkspaceRole | None,
    share: ShareAccessProtocol | None = None,
    now: datetime | None = None,
) -> bool:
    if role is None and not is_share_active(share, now):
        return False

    if doc.owner_id == actor_id:
        return True

    if role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        return True

    return bool(is_share_active(share, now) and share is not None and share.permission == "write")


def can_upload_version(
    actor_id: uuid.UUID,
    doc: DocumentAccessProtocol,
    role: WorkspaceRole | None,
    share: ShareAccessProtocol | None = None,
    now: datetime | None = None,
) -> bool:
    if role is None and not is_share_active(share, now):
        return False

    if doc.owner_id == actor_id:
        return True

    if role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER):
        return True

    return bool(is_share_active(share, now) and share is not None and share.permission == "write")


def can_download_document(
    actor_id: uuid.UUID,
    doc: DocumentAccessProtocol,
    role: WorkspaceRole | None,
    share: ShareAccessProtocol | None = None,
    now: datetime | None = None,
) -> bool:
    return can_view_document(actor_id=actor_id, doc=doc, role=role, share=share, now=now)


def can_manage_shares(
    actor_id: uuid.UUID,
    doc: DocumentAccessProtocol,
    role: WorkspaceRole | None,
) -> bool:
    if doc.owner_id == actor_id:
        return True
    return role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN)


def can_grant_share(
    granter_role: WorkspaceRole | None,
    granter_is_doc_owner: bool,
    requested_permission: str,
) -> bool:
    if granter_is_doc_owner or granter_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        return True

    return bool(granter_role == WorkspaceRole.MEMBER and requested_permission == "read")


def enforce_document_access(
    has_access: bool,
    is_workspace_member: bool,
    action_name: str = "perform this action",
) -> None:
    if not is_workspace_member:
        raise NotFoundError("Document not found", code="NOT_FOUND")
    if not has_access:
        raise ForbiddenError(f"Insufficient permissions to {action_name}", code="FORBIDDEN")
