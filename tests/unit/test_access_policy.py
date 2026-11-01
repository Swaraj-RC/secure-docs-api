import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.workspace import WorkspaceRole
from app.policies.access import (
    can_create_document,
    can_delete_workspace,
    can_download_document,
    can_edit_document,
    can_grant_share,
    can_manage_members,
    can_manage_shares,
    can_manage_workspace,
    can_upload_version,
    can_view_audit_logs,
    can_view_document,
    can_view_workspace,
    enforce_document_access,
)


@dataclass
class MockDocument:
    owner_id: uuid.UUID
    classification: str
    status: str = "active"


@dataclass
class MockShare:
    user_id: uuid.UUID
    permission: str
    expires_at: datetime | None = None


def test_workspace_policy_matrix() -> None:
    # can_view_workspace
    assert can_view_workspace(WorkspaceRole.VIEWER) is True
    assert can_view_workspace(WorkspaceRole.MEMBER) is True
    assert can_view_workspace(None) is False

    # can_manage_workspace
    assert can_manage_workspace(WorkspaceRole.OWNER) is True
    assert can_manage_workspace(WorkspaceRole.ADMIN) is True
    assert can_manage_workspace(WorkspaceRole.MEMBER) is False
    assert can_manage_workspace(WorkspaceRole.VIEWER) is False

    # can_delete_workspace
    assert can_delete_workspace(WorkspaceRole.OWNER) is True
    assert can_delete_workspace(WorkspaceRole.ADMIN) is False

    # can_manage_members
    assert can_manage_members(WorkspaceRole.OWNER) is True
    assert can_manage_members(WorkspaceRole.ADMIN) is True
    assert can_manage_members(WorkspaceRole.MEMBER) is False

    # can_create_document
    assert can_create_document(WorkspaceRole.OWNER) is True
    assert can_create_document(WorkspaceRole.ADMIN) is True
    assert can_create_document(WorkspaceRole.MEMBER) is True
    assert can_create_document(WorkspaceRole.VIEWER) is False
    assert can_create_document(None) is False

    # can_view_audit_logs
    assert can_view_audit_logs(WorkspaceRole.OWNER) is True
    assert can_view_audit_logs(WorkspaceRole.ADMIN) is True
    assert can_view_audit_logs(WorkspaceRole.MEMBER) is False
    assert can_view_audit_logs(WorkspaceRole.VIEWER) is False
    assert can_view_audit_logs(None) is False


@pytest.mark.parametrize(
    "role,classification,is_owner,has_share,expected",
    [
        # PUBLIC
        (WorkspaceRole.OWNER, "public", False, False, True),
        (WorkspaceRole.ADMIN, "public", False, False, True),
        (WorkspaceRole.MEMBER, "public", False, False, True),
        (WorkspaceRole.VIEWER, "public", False, False, True),
        (None, "public", False, False, False),
        (None, "public", False, True, True),
        # INTERNAL
        (WorkspaceRole.OWNER, "internal", False, False, True),
        (WorkspaceRole.ADMIN, "internal", False, False, True),
        (WorkspaceRole.MEMBER, "internal", False, False, True),
        (WorkspaceRole.VIEWER, "internal", False, False, True),
        (None, "internal", False, False, False),
        (None, "internal", False, True, True),
        # CONFIDENTIAL
        (WorkspaceRole.OWNER, "confidential", False, False, True),
        (WorkspaceRole.ADMIN, "confidential", False, False, True),
        (WorkspaceRole.MEMBER, "confidential", True, False, True),
        (WorkspaceRole.MEMBER, "confidential", False, False, False),
        (WorkspaceRole.MEMBER, "confidential", False, True, True),
        (WorkspaceRole.VIEWER, "confidential", False, False, False),
        # RESTRICTED
        (WorkspaceRole.OWNER, "restricted", False, False, True),
        (WorkspaceRole.ADMIN, "restricted", False, False, True),
        (WorkspaceRole.MEMBER, "restricted", True, False, True),
        (WorkspaceRole.MEMBER, "restricted", False, False, False),
        (WorkspaceRole.VIEWER, "restricted", True, False, True),
        (WorkspaceRole.VIEWER, "restricted", False, False, False),
        (WorkspaceRole.VIEWER, "restricted", False, True, True),
        (None, "restricted", False, False, False),
    ],
)
def test_can_view_document_matrix(
    role: WorkspaceRole | None,
    classification: str,
    is_owner: bool,
    has_share: bool,
    expected: bool,
) -> None:
    actor_id = uuid.uuid4()
    doc_owner = actor_id if is_owner else uuid.uuid4()
    doc = MockDocument(owner_id=doc_owner, classification=classification)
    share = MockShare(user_id=actor_id, permission="read") if has_share else None

    result = can_view_document(actor_id=actor_id, doc=doc, role=role, share=share)
    assert result is expected
    assert can_download_document(actor_id=actor_id, doc=doc, role=role, share=share) is expected


def test_can_view_document_expired_share() -> None:
    actor_id = uuid.uuid4()
    doc = MockDocument(owner_id=uuid.uuid4(), classification="confidential")
    expired_share = MockShare(
        user_id=actor_id,
        permission="read",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    result = can_view_document(
        actor_id=actor_id,
        doc=doc,
        role=WorkspaceRole.MEMBER,
        share=expired_share,
    )
    assert result is False


def test_can_edit_document_matrix() -> None:
    actor_id = uuid.uuid4()
    other_id = uuid.uuid4()

    doc = MockDocument(owner_id=other_id, classification="internal")
    assert can_edit_document(actor_id, doc, WorkspaceRole.OWNER) is True
    assert can_edit_document(actor_id, doc, WorkspaceRole.ADMIN) is True
    assert can_edit_document(actor_id, doc, WorkspaceRole.MEMBER) is False
    assert can_edit_document(actor_id, doc, WorkspaceRole.VIEWER) is False

    # Owner of doc can always edit
    doc_owned = MockDocument(owner_id=actor_id, classification="internal")
    assert can_edit_document(actor_id, doc_owned, WorkspaceRole.MEMBER) is True

    # Active write share allows edit
    write_share = MockShare(user_id=actor_id, permission="write")
    read_share = MockShare(user_id=actor_id, permission="read")
    assert can_edit_document(actor_id, doc, WorkspaceRole.MEMBER, share=write_share) is True
    assert can_edit_document(actor_id, doc, WorkspaceRole.MEMBER, share=read_share) is False

    # Archived doc cannot be edited by anyone
    doc_archived = MockDocument(owner_id=actor_id, classification="internal", status="archived")
    assert can_edit_document(actor_id, doc_archived, WorkspaceRole.OWNER) is False


def test_can_upload_version_matrix() -> None:
    actor_id = uuid.uuid4()
    doc = MockDocument(owner_id=actor_id, classification="internal")
    assert can_upload_version(actor_id, doc, WorkspaceRole.MEMBER) is True


def test_can_manage_shares_matrix() -> None:
    actor_id = uuid.uuid4()
    other_id = uuid.uuid4()

    doc = MockDocument(owner_id=other_id, classification="internal")
    assert can_manage_shares(actor_id, doc, WorkspaceRole.OWNER) is True
    assert can_manage_shares(actor_id, doc, WorkspaceRole.ADMIN) is True
    assert can_manage_shares(actor_id, doc, WorkspaceRole.MEMBER) is False

    doc_owned = MockDocument(owner_id=actor_id, classification="internal")
    assert can_manage_shares(actor_id, doc_owned, WorkspaceRole.MEMBER) is True


def test_can_grant_share_limits() -> None:
    # Workspace admin/owner can grant read or write
    assert can_grant_share(WorkspaceRole.ADMIN, False, "read") is True
    assert can_grant_share(WorkspaceRole.ADMIN, False, "write") is True

    # Document owner can grant read or write
    assert can_grant_share(WorkspaceRole.MEMBER, True, "read") is True
    assert can_grant_share(WorkspaceRole.MEMBER, True, "write") is True

    # Regular member holding read access cannot grant write
    assert can_grant_share(WorkspaceRole.MEMBER, False, "read") is True
    assert can_grant_share(WorkspaceRole.MEMBER, False, "write") is False

    # Viewer cannot grant shares
    assert can_grant_share(WorkspaceRole.VIEWER, False, "read") is False


def test_enforce_document_access_leakage_rule() -> None:
    with pytest.raises(NotFoundError) as nf_info:
        enforce_document_access(has_access=False, is_workspace_member=False, action_name="view")
    assert nf_info.value.code == "NOT_FOUND"

    with pytest.raises(ForbiddenError) as fb_info:
        enforce_document_access(has_access=False, is_workspace_member=True, action_name="view")
    assert fb_info.value.code == "FORBIDDEN"
