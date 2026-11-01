import pytest
from httpx import AsyncClient

from tests.factories import user_payload


@pytest.mark.asyncio
async def test_auth_login_rate_limiting(async_client: AsyncClient) -> None:
    payload = user_payload(email="ratelimit.target@corp-vault.com")
    reg = await async_client.post("/api/v1/auth/register", json=payload)
    assert reg.status_code == 201

    # First 10 login attempts are allowed
    for _ in range(10):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "WrongPassword99!"},
        )
        assert res.status_code in (401, 200)

    # 11th attempt within the minute is blocked by rate limiter (429)
    res_limited = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert res_limited.status_code == 429
    body = res_limited.json()
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in res_limited.headers


@pytest.mark.asyncio
async def test_security_headers_present_on_all_responses(async_client: AsyncClient) -> None:
    res = await async_client.get("/api/v1/healthz")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert headers.get("X-XSS-Protection") == "0"
    assert "geolocation=()" in headers.get("Permissions-Policy", "")
    assert "default-src 'none'" in headers.get("Content-Security-Policy", "")
    assert "X-Request-ID" in headers


@pytest.mark.asyncio
async def test_content_length_oversized_payload_rejected_upfront(
    async_client: AsyncClient,
) -> None:
    # 50 MB Content-Length sent to a standard JSON route (max 10 MB)
    res = await async_client.post(
        "/api/v1/auth/login",
        headers={"Content-Length": str(50 * 1024 * 1024)},
        content=b"{}",
    )
    assert res.status_code == 413
    body = res.json()
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
