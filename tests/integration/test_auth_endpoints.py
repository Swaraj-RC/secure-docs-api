import pytest
from httpx import AsyncClient

from tests.factories import user_payload


@pytest.mark.asyncio
async def test_register_and_login_lifecycle(async_client: AsyncClient) -> None:
    data = user_payload(
        email="alex.chen@cyber-vault.io",
        password="Secure-Master-Key#2026",
        full_name="Alex Chen",
    )

    # 1. Register
    reg_res = await async_client.post("/api/v1/auth/register", json=data)
    assert reg_res.status_code == 201
    user = reg_res.json()
    assert user["email"] == "alex.chen@cyber-vault.io"
    assert user["full_name"] == "Alex Chen"
    assert "id" in user
    assert "password" not in user

    # 2. Duplicate registration fails
    dup_res = await async_client.post("/api/v1/auth/register", json=data)
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "CONFLICT"

    # 3. Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"

    # 4. /auth/me with Bearer token
    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alex.chen@cyber-vault.io"


@pytest.mark.asyncio
async def test_login_invalid_credentials_and_lockout(async_client: AsyncClient) -> None:
    data = user_payload(
        email="target.user@security-lab.internal",
        password="Real-Password-9988!",
    )
    await async_client.post("/api/v1/auth/register", json=data)

    # 4 bad attempts
    for _ in range(4):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": data["email"], "password": "WrongPassword!"},
        )
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # 5th bad attempt triggers lockout
    res_5th = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": "WrongPassword!"},
    )
    assert res_5th.status_code == 401

    # 6th attempt (even with CORRECT password) is locked out
    res_locked = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    assert res_locked.status_code == 401
    assert res_locked.json()["error"]["code"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection(async_client: AsyncClient) -> None:
    data = user_payload(email="rotation.test@meridian.io")
    await async_client.post("/api/v1/auth/register", json=data)

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    t1 = login_res.json()
    r1 = t1["refresh_token"]

    # First rotation: r1 -> r2 (success)
    ref1_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
    assert ref1_res.status_code == 200
    t2 = ref1_res.json()
    r2 = t2["refresh_token"]
    assert r2 != r1

    # REPLAY ATTACK: Attacker replays old token r1!
    replay_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
    assert replay_res.status_code == 401
    assert replay_res.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    # Family revocation: Legitimate token r2 is now ALSO revoked due to replay detection
    ref2_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": r2})
    assert ref2_res.status_code == 401
    assert ref2_res.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"


@pytest.mark.asyncio
async def test_logout_revokes_token(async_client: AsyncClient) -> None:
    data = user_payload(email="logout.user@domain.com")
    await async_client.post("/api/v1/auth/register", json=data)

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": data["email"], "password": data["password"]},
    )
    tokens = login_res.json()

    # Logout requires valid Bearer token
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout_res.status_code == 200

    # Subsequent refresh with revoked token triggers reuse / invalid error
    ref_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert ref_res.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_unauthorized(async_client: AsyncClient) -> None:
    res = await async_client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
