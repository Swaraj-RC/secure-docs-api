from datetime import UTC, datetime, timedelta
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
async def test_grant_list_revoke_share_lifecycle(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "share.owner@corp.internal")
    auditor, auditor_tok = await _create_user_and_auth(
        async_client, "external.auditor@auditfirm.com"
    )

    # 1. Create workspace & restricted document
    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Compliance Core", "slug": "compliance-core-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Q3 SOC 2 Audit Report", "classification": "restricted"},
    )
    doc_id = doc_res.json()["id"]

    # Before share: external auditor gets 404
    pre_share = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert pre_share.status_code == 404

    # 2. Grant READ share to external auditor by email
    share_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": auditor["email"], "permission": "read"},
    )
    assert share_res.status_code == 201
    share = share_res.json()
    share_id = share["id"]
    assert share["permission"] == "read"
    assert share["user_id"] == auditor["id"]

    # External auditor can now read the restricted document
    read_res = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert read_res.status_code == 200
    assert read_res.json()["title"] == "Q3 SOC 2 Audit Report"

    # External auditor with READ permission cannot edit document (403)
    edit_denied = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
        json={"title": "Tampered Title"},
    )
    assert edit_denied.status_code == 403

    # 3. Upgrade share to WRITE
    upgrade_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"user_id": auditor["id"], "permission": "write"},
    )
    assert upgrade_res.status_code == 201
    assert upgrade_res.json()["permission"] == "write"

    # External auditor can now update document
    edit_allowed = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
        json={"title": "Q3 SOC 2 Audit Report — Verified"},
    )
    assert edit_allowed.status_code == 200
    assert edit_allowed.json()["title"] == "Q3 SOC 2 Audit Report — Verified"

    # 4. List shares
    shares_list = await async_client.get(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert shares_list.status_code == 200
    assert len(shares_list.json()) == 1

    # 5. Revoke share
    rev_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}/shares/{share_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert rev_res.status_code == 204

    # After revocation, external auditor access drops to 404
    post_revoke = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {auditor_tok}"},
    )
    assert post_revoke.status_code == 404


@pytest.mark.asyncio
async def test_cannot_grant_more_than_held(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "rule.owner@corp.internal")
    member_user, member_tok = await _create_user_and_auth(async_client, "rule.mem@corp.internal")
    collaborator, _collab_tok = await _create_user_and_auth(async_client, "collab@partner.org")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Research Group", "slug": "research-grp-2026"},
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
        json={"title": "Quarterly Objectives", "classification": "internal"},
    )
    doc_id = doc_res.json()["id"]

    # Ordinary workspace member attempts to grant WRITE -> forbidden
    cant_grant_write = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={"email": collaborator["email"], "permission": "write"},
    )
    assert cant_grant_write.status_code == 403

    # Ordinary workspace member can grant READ
    can_grant_read = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={"email": collaborator["email"], "permission": "read"},
    )
    assert can_grant_read.status_code == 201
    assert can_grant_read.json()["permission"] == "read"


@pytest.mark.asyncio
async def test_expired_shares_ignored_at_query_time(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "expiry.owner@corp.internal")
    contractor, contractor_tok = await _create_user_and_auth(async_client, "contractor@temp.agency")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Temporary Projects", "slug": "temp-proj-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Time-sensitive Briefing", "classification": "restricted"},
    )
    doc_id = doc_res.json()["id"]

    # Grant share that already expired 1 hour ago
    past_expiry = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    share_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={
            "email": contractor["email"],
            "permission": "read",
            "expires_at": past_expiry,
        },
    )
    assert share_res.status_code == 201

    # Contractor accessing document with expired share gets 404
    access_attempt = await async_client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {contractor_tok}"},
    )
    assert access_attempt.status_code == 404

    # List shares endpoint filters out expired shares
    list_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 0
