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
async def test_audit_log_recorded_on_document_lifecycle(async_client: AsyncClient) -> None:
    owner, owner_tok = await _create_user_and_auth(async_client, "audit.officer@defense-gov.us")

    # 1. Create workspace
    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Defense Records", "slug": "defense-records-2026"},
    )
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]

    # 2. Create document -> doc.create logged
    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Airframe Structural Specifications", "classification": "confidential"},
    )
    assert doc_res.status_code == 201
    doc_id = doc_res.json()["id"]

    # 3. Update document -> doc.update logged
    update_res = await async_client.patch(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Airframe Structural Specifications - Rev B"},
    )
    assert update_res.status_code == 200

    # 4. Soft delete document -> doc.delete logged
    del_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert del_res.status_code == 204

    # 5. Restore document -> doc.restore logged
    restore_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/restore",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert restore_res.status_code == 200

    # 6. Verify audit logs via GET /workspaces/{ws_id}/audit-logs
    logs_res = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert logs_res.status_code == 200
    logs_data = logs_res.json()
    assert logs_data["total"] >= 5

    actions = [item["action"] for item in logs_data["items"]]
    assert "ws.create" in actions
    assert "doc.create" in actions
    assert "doc.update" in actions
    assert "doc.delete" in actions
    assert "doc.restore" in actions

    # Verify GET /audit-logs/me
    my_logs_res = await async_client.get(
        "/api/v1/audit-logs/me",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert my_logs_res.status_code == 200
    my_logs = my_logs_res.json()
    assert my_logs["total"] >= 5
    for item in my_logs["items"]:
        assert item["actor_id"] == owner["id"]


@pytest.mark.asyncio
async def test_audit_log_access_control_and_leakage_rule(
    async_client: AsyncClient,
) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "owner.audit@corp.org")
    member, member_tok = await _create_user_and_auth(async_client, "regular.member@corp.org")
    _stranger, stranger_tok = await _create_user_and_auth(async_client, "stranger@corp.org")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Classified Lab", "slug": "classified-lab-01"},
    )
    ws_id = ws_res.json()["id"]

    # Add member to workspace
    add_mem = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": member["email"], "role": "member"},
    )
    assert add_mem.status_code == 201

    # Owner can access audit logs
    owner_get = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_get.status_code == 200

    # Member gets 403 Forbidden
    member_get = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert member_get.status_code == 403

    # Stranger (non-member) gets 404 Not Found (Leakage prevention)
    stranger_get = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_get.status_code == 404


@pytest.mark.asyncio
async def test_audit_log_filtering_and_share_events(async_client: AsyncClient) -> None:
    owner, owner_tok = await _create_user_and_auth(async_client, "lead.ciso@vault-sec.io")
    collaborator, _ = await _create_user_and_auth(async_client, "collab.engineer@vault-sec.io")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Security Operations", "slug": "secops-vault-2026"},
    )
    ws_id = ws_res.json()["id"]

    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Master Root Key Ceremony Procedure", "classification": "restricted"},
    )
    doc_id = doc_res.json()["id"]

    # Share document -> share.create
    share_res = await async_client.post(
        f"/api/v1/documents/{doc_id}/shares",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": collaborator["email"], "permission": "read"},
    )
    assert share_res.status_code == 201
    share_id = share_res.json()["id"]

    # Revoke share -> share.revoke
    rev_res = await async_client.delete(
        f"/api/v1/documents/{doc_id}/shares/{share_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert rev_res.status_code == 204

    # Query filtered by action=share.create
    filtered_action = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs?action=share.create",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert filtered_action.status_code == 200
    res_items = filtered_action.json()["items"]
    assert len(res_items) == 1
    assert res_items[0]["action"] == "share.create"
    assert res_items[0]["resource_type"] == "document_share"

    # Query filtered by resource_type=document
    filtered_resource = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs?resource_type=document",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert filtered_resource.status_code == 200
    for item in filtered_resource.json()["items"]:
        assert item["resource_type"] == "document"

    # Query filtered by actor_id
    filtered_actor = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-logs?actor_id={owner['id']}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert filtered_actor.status_code == 200
    for item in filtered_actor.json()["items"]:
        assert item["actor_id"] == owner["id"]
