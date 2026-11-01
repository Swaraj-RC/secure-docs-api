import io
from typing import Any

import pytest
from httpx import AsyncClient

from tests.factories import user_payload

VALID_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
EXECUTABLE_BYTES = (
    b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00>\x00\x01\x00\x00\x00"
)


async def _create_user_and_auth(client: AsyncClient, email: str) -> tuple[dict[str, Any], str]:
    payload = user_payload(email=email)
    res = await client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    user = res.json()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    token = login.json()["access_token"]
    return user, token


@pytest.mark.asyncio
async def test_successful_file_upload_and_versioning(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "upload.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Engineering Specs", "slug": "eng-specs-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Q3 Infrastructure Topology", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]
    assert doc_res.json()["current_version_id"] is None

    v1_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("infra-v1.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")},
    )
    assert v1_res.status_code == 201
    v1 = v1_res.json()
    assert v1["version_number"] == 1
    assert v1["original_filename"] == "infra-v1.pdf"
    assert v1["mime_type"] == "application/pdf"
    assert v1["size_bytes"] == len(VALID_PDF_BYTES)
    assert len(v1["checksum_sha256"]) == 64

    doc_after_v1 = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert doc_after_v1.json()["current_version_id"] == v1["id"]

    v2_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("network-topology.png", io.BytesIO(VALID_PNG_BYTES), "image/png")},
    )
    assert v2_res.status_code == 201
    v2 = v2_res.json()
    assert v2["version_number"] == 2
    assert v2["original_filename"] == "network-topology.png"
    assert v2["mime_type"] == "image/png"

    doc_after_v2 = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert doc_after_v2.json()["current_version_id"] == v2["id"]

    versions_list = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert versions_list.status_code == 200
    versions = versions_list.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1


@pytest.mark.asyncio
async def test_disallowed_mime_type_rejected(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "mime.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Security Vault", "slug": "security-vault-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Binary Test", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    bad_upload = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("payload.pdf", io.BytesIO(EXECUTABLE_BYTES), "application/pdf")},
    )
    assert bad_upload.status_code == 422
    assert bad_upload.json()["error"]["code"] == "UPLOAD_MIME_MISMATCH"


@pytest.mark.asyncio
async def test_empty_file_rejected(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "empty.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Audit Records", "slug": "audit-records-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Empty File Test", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    empty_upload = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert empty_upload.status_code == 422
    assert empty_upload.json()["error"]["code"] == "EMPTY_FILE"


@pytest.mark.asyncio
async def test_oversized_file_rejected(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "size.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Large Files Hub", "slug": "large-files-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Size Test", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    from app.core.config import Settings

    monkeypatch.setattr(Settings, "max_upload_size_bytes", property(lambda self: 100))

    oversized_data = VALID_PDF_BYTES + (b"A" * 200)
    over_upload = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("oversized.pdf", io.BytesIO(oversized_data), "application/pdf")},
    )
    assert over_upload.status_code == 422
    assert over_upload.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_unauthorized_and_stranger_upload_blocked(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "perm.owner@corp.internal")
    viewer_user, viewer_tok = await _create_user_and_auth(async_client, "perm.viewer@corp.internal")
    _stranger, stranger_tok = await _create_user_and_auth(async_client, "perm.stranger@other.com")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Permissions Test Hub", "slug": "perm-test-hub-2026"},
    )
    ws_id = ws_res.json()["id"]

    await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": viewer_user["email"], "role": "viewer"},
    )

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Restricted Uploads", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    stranger_upload = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {stranger_tok}"},
        files={"file": ("test.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")},
    )
    assert stranger_upload.status_code == 404

    viewer_upload = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {viewer_tok}"},
        files={"file": ("test.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")},
    )
    assert viewer_upload.status_code == 403
