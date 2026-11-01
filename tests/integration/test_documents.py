from typing import Any

import pytest
from httpx import AsyncClient

from tests.factories import user_payload


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
async def test_document_lifecycle_and_leakage(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "owner.doc@corp.internal")
    member_user, member_tok = await _create_user_and_auth(async_client, "member.doc@corp.internal")
    _stranger, stranger_tok = await _create_user_and_auth(async_client, "stranger.doc@other.org")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Compliance Documents Hub", "slug": "compliance-hub-2026"},
    )
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]

    add_mem = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": member_user["email"], "role": "member"},
    )
    assert add_mem.status_code == 201

    create_doc = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={
            "title": "Vendor Security Assessment 2026",
            "description": "SOC 2 Type II audit report analysis for Cloudflare and AWS",
            "classification": "internal",
        },
    )
    assert create_doc.status_code == 201
    doc = create_doc.json()
    doc_id = doc["id"]
    assert doc["title"] == "Vendor Security Assessment 2026"
    assert doc["status"] == "draft"
    assert doc["classification"] == "internal"
    assert doc["owner_id"] == member_user["id"]
    assert doc["deleted_at"] is None

    stranger_get = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_get.status_code == 404
    assert stranger_get.json()["error"]["code"] in ("NOT_FOUND", "DOCUMENT_NOT_FOUND")

    stranger_create = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {stranger_tok}"},
        json={"title": "Unauthorized Document"},
    )
    assert stranger_create.status_code == 404

    owner_get = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_get.status_code == 200
    assert owner_get.json()["id"] == doc_id

    patch_res = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={"title": "Vendor Security Assessment 2026 — Final", "status": "active"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Vendor Security Assessment 2026 — Final"
    assert patch_res.json()["status"] == "active"

    del_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert del_res.status_code == 204

    post_del_get = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert post_del_get.status_code == 404

    list_res = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["items"]) == 0

    member_restore = await async_client.post(
        f"/api/v1/documents/{doc_id}/restore",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert member_restore.status_code == 403

    stranger_restore = await async_client.post(
        f"/api/v1/documents/{doc_id}/restore",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_restore.status_code == 404

    owner_restore = await async_client.post(
        f"/api/v1/documents/{doc_id}/restore",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_restore.status_code == 200
    assert owner_restore.json()["deleted_at"] is None

    restored_get = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert restored_get.status_code == 200
    assert restored_get.json()["title"] == "Vendor Security Assessment 2026 — Final"


@pytest.mark.asyncio
async def test_document_query_filters_and_sorting(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "filter.owner@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Legal Repository", "slug": "legal-repo-2026"},
    )
    ws_id = ws_res.json()["id"]

    docs_data = [
        {
            "title": "Alpha Vendor MSA",
            "description": "Master Service Agreement",
            "classification": "public",
        },
        {
            "title": "Beta Employment Contract",
            "description": "Standard executive agreement",
            "classification": "internal",
        },
        {
            "title": "Gamma Secret Merger",
            "description": "Strictly NDA protected",
            "classification": "restricted",
        },
    ]
    created_ids = []
    for d in docs_data:
        r = await async_client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            headers={"Authorization": f"Bearer {owner_tok}"},
            json=d,
        )
        assert r.status_code == 201
        created_ids.append(r.json()["id"])

    q_title = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?q=Alpha",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert q_title.status_code == 200
    items = q_title.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Alpha Vendor MSA"

    q_desc = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?q=Strictly",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert q_desc.status_code == 200
    assert len(q_desc.json()["items"]) == 1
    assert q_desc.json()["items"][0]["title"] == "Gamma Secret Merger"

    class_res = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?classification=restricted",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert class_res.status_code == 200
    assert len(class_res.json()["items"]) == 1
    assert class_res.json()["items"][0]["classification"] == "restricted"

    sort_asc = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?sort=+title",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert sort_asc.status_code == 200
    titles = [d["title"] for d in sort_asc.json()["items"]]
    assert titles == sorted(titles)

    sort_desc = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?sort=-title",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert sort_desc.status_code == 200
    titles_desc = [d["title"] for d in sort_desc.json()["items"]]
    assert titles_desc == sorted(titles, reverse=True)

    sort_bad = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?sort=non_existent_column",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert sort_bad.status_code == 422


@pytest.mark.asyncio
async def test_classification_access_matrix(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "matrix.owner@corp.internal")
    member_user, member_tok = await _create_user_and_auth(async_client, "matrix.mem@corp.internal")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Executive Board Vault", "slug": "board-vault-2026"},
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
        json={
            "title": "Board Resolution 2026-Q1",
            "classification": "restricted",
        },
    )
    doc_id = doc_res.json()["id"]

    member_read = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert member_read.status_code == 403
    assert member_read.json()["error"]["code"] == "FORBIDDEN"

    member_list = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert member_list.status_code == 200
    assert not any(d["id"] == doc_id for d in member_list.json()["items"])
