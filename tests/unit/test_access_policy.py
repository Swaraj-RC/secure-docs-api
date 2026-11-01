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


@pytest.mark.parametrize(
    "role,classification,is_owner,has_share,expected",
    [
        # Non-member with no share has no access
        (None, "public", False, False, False),
        (None, "internal", False, True, True),  # valid share allows access
        (None, "restricted", True, False, False),  # non-member has no access
        # Workspace member who is doc owner always has access
        (WorkspaceRole.VIEWER, "restricted", True, False, True),
        (WorkspaceRole.MEMBER, "restricted", True, False, True),
        # Owner & Admin always have access to all classifications
        (WorkspaceRole.OWNER, "restricted", False, False, True),
        (WorkspaceRole.ADMIN, "confidential", False, False, True),
        # Member: public/internal allowed; confidential/restricted requires share or ownership
        (WorkspaceRole.MEMBER, "public", False, False, True),
        (WorkspaceRole.MEMBER, "internal", False, False, True),
        (WorkspaceRole.MEMBER, "confidential", False, False, False),
        (WorkspaceRole.MEMBER, "confidential", False, True, True),
        (WorkspaceRole.MEMBER, "restricted", False, False, False),
        # Viewer: public/internal allowed; confidential/restricted forbidden unless share
        (WorkspaceRole.VIEWER, "public", False, False, True),
        (WorkspaceRole.VIEWER, "internal", False, False, True),
        (WorkspaceRole.VIEWER, "confidential", False, False, False),
        (WorkspaceRole.VIEWER, "restricted", False, True, True),
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
    expired = MockShare(
        user_id=actor_id,
        permission="read",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # Member with expired share on confidential doc cannot view
    assert can_view_document(actor_id, doc, WorkspaceRole.MEMBER, share=expired) is False


def test_can_edit_document_matrix() -> None:
    actor_id = uuid.uuid4()
    own_doc = MockDocument(owner_id=actor_id, classification="internal")
    other_doc = MockDocument(owner_id=uuid.uuid4(), classification="internal")

    # Doc owner can edit
    assert can_edit_document(actor_id, own_doc, WorkspaceRole.MEMBER) is True

    # Owner & Admin can edit any doc
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.OWNER) is True
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.ADMIN) is True

    # Regular member cannot edit other's doc without write share
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.MEMBER) is False
    read_share = MockShare(user_id=actor_id, permission="read")
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.MEMBER, share=read_share) is False

    write_share = MockShare(user_id=actor_id, permission="write")
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.MEMBER, share=write_share) is True

    # Viewer cannot edit even with own doc (hypothetical)
    assert can_edit_document(actor_id, other_doc, WorkspaceRole.VIEWER) is False


def test_can_upload_version_matrix() -> None:
    actor_id = uuid.uuid4()
    doc = MockDocument(owner_id=uuid.uuid4(), classification="internal")

    # Member can upload version to workspace doc
    assert can_upload_version(actor_id, doc, WorkspaceRole.MEMBER) is True
    assert can_upload_version(actor_id, doc, WorkspaceRole.ADMIN) is True
    assert can_upload_version(actor_id, doc, WorkspaceRole.OWNER) is True

    # Viewer cannot upload version
    assert can_upload_version(actor_id, doc, WorkspaceRole.VIEWER) is False

    # Non-member with write share can upload version
    write_share = MockShare(user_id=actor_id, permission="write")
    assert can_upload_version(actor_id, doc, None, share=write_share) is True


def test_can_manage_shares_matrix() -> None:
    actor_id = uuid.uuid4()
    own_doc = MockDocument(owner_id=actor_id, classification="internal")
    other_doc = MockDocument(owner_id=uuid.uuid4(), classification="internal")

    assert can_manage_shares(actor_id, own_doc, WorkspaceRole.MEMBER) is True
    assert can_manage_shares(actor_id, other_doc, WorkspaceRole.OWNER) is True
    assert can_manage_shares(actor_id, other_doc, WorkspaceRole.ADMIN) is True
    assert can_manage_shares(actor_id, other_doc, WorkspaceRole.MEMBER) is False
    assert can_manage_shares(actor_id, other_doc, WorkspaceRole.VIEWER) is False


def test_can_grant_share_limits() -> None:
    assert can_grant_share(WorkspaceRole.OWNER, False, "write") is True
    assert can_grant_share(WorkspaceRole.ADMIN, False, "write") is True
    assert can_grant_share(None, True, "write") is True  # doc owner
    assert can_grant_share(WorkspaceRole.MEMBER, False, "read") is True
    assert can_grant_share(WorkspaceRole.MEMBER, False, "write") is False
    assert can_grant_share(WorkspaceRole.VIEWER, False, "read") is False


def test_enforce_document_access_leakage_rule() -> None:
    # Non-member always gets 404 (do not leak existence)
    with pytest.raises(NotFoundError) as not_found:
        enforce_document_access(has_access=False, is_workspace_member=False)
    assert not_found.value.code == "NOT_FOUND"

    # Member without permission gets 403
    with pytest.raises(ForbiddenError) as forbidden:
        enforce_document_access(has_access=False, is_workspace_member=True)
    assert forbidden.value.code == "FORBIDDEN"

    # Member with permission succeeds
    enforce_document_access(has_access=True, is_workspace_member=True)
