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
async def test_workspace_crud_and_leakage_rule(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "owner.ws@corp.internal")
    _stranger, stranger_tok = await _create_user_and_auth(async_client, "stranger@other.com")

    # 1. Create workspace
    create_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Engineering Core", "slug": "eng-core-2026"},
    )
    assert create_res.status_code == 201
    ws = create_res.json()
    ws_id = ws["id"]
    assert ws["name"] == "Engineering Core"
    assert ws["slug"] == "eng-core-2026"

    # 2. Duplicate slug fails
    dup_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Duplicate Slug Test", "slug": "eng-core-2026"},
    )
    assert dup_res.status_code == 409

    # 3. Leakage rule: stranger gets 404, NOT 403, when trying to view or access ws_id
    stranger_get = await async_client.get(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_get.status_code == 404
    assert stranger_get.json()["error"]["code"] == "NOT_FOUND"

    # 4. List my workspaces: owner sees it, stranger sees empty list
    owner_list = await async_client.get(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_list.status_code == 200
    assert owner_list.json()["total"] == 1

    stranger_list = await async_client.get(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {stranger_tok}"},
    )
    assert stranger_list.status_code == 200
    assert stranger_list.json()["total"] == 0

    # 5. Update workspace name
    patch_res = await async_client.patch(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Engineering Operations"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Engineering Operations"


@pytest.mark.asyncio
async def test_workspace_roles_and_member_permissions(async_client: AsyncClient) -> None:
    _, owner_tok = await _create_user_and_auth(async_client, "ws.owner@nexus.io")
    admin_user, admin_tok = await _create_user_and_auth(async_client, "ws.admin@nexus.io")
    member_user, member_tok = await _create_user_and_auth(async_client, "ws.member@nexus.io")
    viewer_user, viewer_tok = await _create_user_and_auth(async_client, "ws.viewer@nexus.io")

    # Create workspace as owner
    ws = (
        await async_client.post(
            "/api/v1/workspaces",
            headers={"Authorization": f"Bearer {owner_tok}"},
            json={"name": "Security Ops", "slug": "sec-ops-matrix"},
        )
    ).json()
    ws_id = ws["id"]

    # Owner adds Admin
    add_admin = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": admin_user["email"], "role": "admin"},
    )
    assert add_admin.status_code == 201
    assert add_admin.json()["role"] == "admin"

    # Admin adds Member
    add_member = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"email": member_user["email"], "role": "member"},
    )
    assert add_member.status_code == 201

    # Member tries to add Viewer -> 403 Forbidden
    fail_add = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {member_tok}"},
        json={"email": viewer_user["email"], "role": "viewer"},
    )
    assert fail_add.status_code == 403
    assert fail_add.json()["error"]["code"] == "FORBIDDEN"

    # Admin adds Viewer
    add_viewer = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"email": viewer_user["email"], "role": "viewer"},
    )
    assert add_viewer.status_code == 201

    # List members (all 4 should be listed)
    members_list = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {viewer_tok}"},
    )
    assert members_list.status_code == 200
    assert members_list.json()["total"] == 4

    # Role update: Admin promotes Member to Admin
    role_change = await async_client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{member_user['id']}",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"role": "admin"},
    )
    assert role_change.status_code == 200
    assert role_change.json()["role"] == "admin"

    # Member removal: Member leaves workspace voluntarily
    leave_res = await async_client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{member_user['id']}",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert leave_res.status_code == 200

    # Non-owner tries to delete workspace -> 403
    del_forbidden = await async_client.delete(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert del_forbidden.status_code == 403

    # Owner deletes workspace -> 200
    del_success = await async_client.delete(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert del_success.status_code == 200
