import io
from typing import Any

import pytest
from httpx import AsyncClient

from tests.factories import user_payload

SAMPLE_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n" + (
    b"RECORD_DATA_BLOCK_" * 10
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
async def test_full_download_with_security_headers(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "dl.owner@corp.internal")

    # Create workspace & document
    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Download Test WS", "slug": "dl-test-ws-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Q3 Audit Report", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    # Upload version with Unicode and special characters in filename
    filename = "Audit Report — Q3 (2026).pdf"
    v_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": (filename, io.BytesIO(SAMPLE_PDF_BYTES), "application/pdf")},
    )
    assert v_res.status_code == 201
    vid = v_res.json()["id"]

    # Download full file
    dl_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert dl_res.status_code == 200
    assert dl_res.content == SAMPLE_PDF_BYTES

    # Check security headers
    assert dl_res.headers.get("x-content-type-options") == "nosniff"
    assert dl_res.headers.get("accept-ranges") == "bytes"
    assert dl_res.headers.get("content-type") == "application/pdf"
    assert str(len(SAMPLE_PDF_BYTES)) == dl_res.headers.get("content-length")

    disposition = dl_res.headers.get("content-disposition", "")
    assert "attachment;" in disposition
    assert "filename*=" in disposition


@pytest.mark.asyncio
async def test_range_request_partial_content(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "range.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Range Test WS", "slug": "range-test-ws-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Video Specifications", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    v_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("specs.pdf", io.BytesIO(SAMPLE_PDF_BYTES), "application/pdf")},
    )
    vid = v_res.json()["id"]

    total_len = len(SAMPLE_PDF_BYTES)

    # 1. Closed range bytes=0-15
    r1 = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {owner_tok}", "Range": "bytes=0-15"},
    )
    assert r1.status_code == 206
    assert len(r1.content) == 16
    assert r1.content == SAMPLE_PDF_BYTES[0:16]
    assert r1.headers.get("content-range") == f"bytes 0-15/{total_len}"
    assert r1.headers.get("content-length") == "16"

    # 2. Suffix range bytes=-20 (last 20 bytes)
    r2 = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {owner_tok}", "Range": "bytes=-20"},
    )
    assert r2.status_code == 206
    assert len(r2.content) == 20
    assert r2.content == SAMPLE_PDF_BYTES[-20:]
    assert r2.headers.get("content-range") == f"bytes {total_len - 20}-{total_len - 1}/{total_len}"

    # 3. Invalid range returns 416
    bad_range = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {owner_tok}", "Range": "bytes=99999-199999"},
    )
    assert bad_range.status_code == 416


@pytest.mark.asyncio
async def test_download_leakage_and_permission_checks(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "leak.owner@corp.internal")
    member_user, member_tok = await _create_user_and_auth(async_client, "leak.mem@corp.internal")
    _stranger, stranger_tok = await _create_user_and_auth(async_client, "leak.stranger@other.com")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Confidential Vault", "slug": "conf-vault-2026"},
    )
    ws_id = ws_res.json()["id"]

    await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": member_user["email"], "role": "member"},
    )

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Secret M&A Terms", "classification": "restricted"},
    )
    doc_id = doc_res.json()["id"]

    v_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {owner_tok}"},
        files={"file": ("ma-terms.pdf", io.BytesIO(SAMPLE_PDF_BYTES), "application/pdf")},
    )
    vid = v_res.json()["id"]

    # Stranger download gets 404
    stranger_dl = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_dl.status_code == 404

    # Member download on restricted document gets 403
    member_dl = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions/{vid}/download",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert member_dl.status_code == 403
