from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_superuser
from app.core.errors import ForbiddenError
from app.db.models.user import User
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
async def test_superuser_dependency_unit() -> None:
    normal_user = User(
        email="normal.member@corp-sec.com",
        password_hash="argon2...",
        full_name="Normal User",
        is_superuser=False,
    )
    with pytest.raises(ForbiddenError) as exc_info:
        await get_current_active_superuser(normal_user)
    assert exc_info.value.code == "FORBIDDEN"

    admin_user = User(
        email="super.admin@corp-sec.com",
        password_hash="argon2...",
        full_name="Super Admin",
        is_superuser=True,
    )
    res = await get_current_active_superuser(admin_user)
    assert res == admin_user


@pytest.mark.asyncio
async def test_inactive_user_cannot_authenticate_or_access(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user_data = user_payload(email="inactive.target@corp-sec.com")
    await async_client.post("/api/v1/auth/register", json=user_data)

    stmt = select(User).where(User.email == user_data["email"])
    db_user = (await db_session.scalars(stmt)).one()
    db_user.is_active = False
    await db_session.commit()

    # Login fails for inactive account
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_res.status_code == 401
    assert login_res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_workspace_admin_and_owner_edge_cases(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "ws.owner@corp-sec.com")
    admin1, admin1_tok = await _create_user_and_auth(async_client, "admin1@corp-sec.com")
    admin2, _ = await _create_user_and_auth(async_client, "admin2@corp-sec.com")

    # Create workspace
    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Edge Cases Lab", "slug": "edge-cases-lab-2026"},
    )
    ws_id = ws_res.json()["id"]

    # Update workspace name
    patch_ws = await async_client.patch(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Edge Cases Lab - Renamed"},
    )
    assert patch_ws.status_code == 200
    assert patch_ws.json()["name"] == "Edge Cases Lab - Renamed"

    # Add admin1
    add_a1 = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": admin1["email"], "role": "admin"},
    )
    assert add_a1.status_code == 201

    # Add admin2
    add_a2 = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": admin2["email"], "role": "admin"},
    )
    assert add_a2.status_code == 201

    # Cannot assign owner role directly via add_member
    new_user, _ = await _create_user_and_auth(async_client, "another.user@corp-sec.com")
    bad_owner_add = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": new_user["email"], "role": "owner"},
    )
    assert bad_owner_add.status_code == 422

    # Cannot update member role to owner
    bad_role_update = await async_client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{admin1['id']}",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"role": "owner"},
    )
    assert bad_role_update.status_code == 422

    # Admin1 cannot remove Admin2 (Admins cannot remove other admins)
    admin_rem = await async_client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{admin2['id']}",
        headers={"Authorization": f"Bearer {admin1_tok}"},
    )
    assert admin_rem.status_code == 403
    assert "Admins cannot remove other admins" in admin_rem.json()["error"]["message"]

    # Owner cannot leave/be removed
    owner_rem = await async_client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{_owner['id']}",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_rem.status_code == 403
    assert "Workspace owner cannot leave" in owner_rem.json()["error"]["message"]


@pytest.mark.asyncio
async def test_document_advanced_filters_and_invalid_sort(async_client: AsyncClient) -> None:
    _owner, owner_tok = await _create_user_and_auth(async_client, "filter.officer@corp-sec.com")

    ws_res = await async_client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"name": "Filters Lab", "slug": "filters-lab-2026"},
    )
    ws_id = ws_res.json()["id"]

    # Create document
    doc_res = await async_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"title": "Operational Blueprint Alpha", "classification": "internal"},
    )
    assert doc_res.status_code == 201

    # Invalid sort field raises 422
    bad_sort = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents?sort=nonexistent_field",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert bad_sort.status_code == 422
    assert bad_sort.json()["error"]["code"] == "INVALID_SORT_FIELD"

    # Filter by created_after in the future returns empty
    future_dt = datetime.now(UTC) + timedelta(days=5)
    future_query = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        params={"created_after": future_dt.isoformat()},
    )
    assert future_query.status_code == 200
    assert len(future_query.json()["items"]) == 0

    # Filter by created_before in the future returns document
    past_query = await async_client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {owner_tok}"},
        params={"created_before": future_dt.isoformat()},
    )
    assert past_query.status_code == 200
    assert len(past_query.json()["items"]) == 1


@pytest.mark.asyncio
async def test_account_lockout_recovery_after_expiry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    data = user_payload(
        email="lockout.recovery@corp-sec.com",
        password="ValidPassword123!",
    )
    await async_client.post("/api/v1/auth/register", json=data)

    stmt = select(User).where(User.email == data["email"])
    db_user = (await db_session.scalars(stmt)).one()

    # Simulate account locked in the past
    db_user.failed_login_count = 5
    db_user.locked_until = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    # Login with correct password succeeds and resets lockout counter
    success_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert success_login.status_code == 200
    assert "access_token" in success_login.json()

    # Verify db user counters reset
    await db_session.refresh(db_user)
    assert db_user.failed_login_count == 0
    assert db_user.locked_until is None
