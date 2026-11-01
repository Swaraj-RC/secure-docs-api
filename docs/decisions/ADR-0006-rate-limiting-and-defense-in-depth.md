# ADR-0006: Rate Limiting Strategy, Request Hardening, and HTTP Security Headers

## Context
A public document management API must be fortified against automated brute-force password guessing, credential stuffing, denial of service from unbounded payload streaming, and browser-based vulnerabilities such as MIME confusion and clickjacking.

## Decision
We implement a comprehensive defense-in-depth hardening layer:

1. **Endpoint-Level Rate Limiting:**
   - Integrated SlowAPI backed by client remote address identification (`get_remote_address`).
   - Sensitive endpoints are capped with deliberate thresholds:
     - `POST /auth/login`: 5 requests per minute per IP to prevent brute-force credential stuffing.
     - `POST /auth/register`: 5 requests per minute per IP to curtail bulk bot registration.
     - `POST /documents/{doc_id}/versions`: 10 uploads per minute per IP to mitigate storage exhaustion.
   - 429 responses return the standard RFC 7807 error envelope with error code `RATE_LIMIT_EXCEEDED` and include a `Retry-After` header.

2. **Early Content-Length Verification:**
   - In addition to streaming file size checks in the upload pipeline, an HTTP middleware checks incoming `Content-Length` headers against maximum payload thresholds (`100 MB` for multipart, `10 MB` for standard JSON), failing fast with `413 Payload Too Large` before buffer allocation.

3. **HTTP Security Headers:**
   - Every response receives the following headers:
     - `X-Content-Type-Options: nosniff` (disables MIME sniffing)
     - `X-Frame-Options: DENY` (prevents framing and clickjacking)
     - `Referrer-Policy: no-referrer` (suppresses referrer leakages)
     - `X-XSS-Protection: 0` (disables legacy buggy browser auditors)
     - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
     - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`
     - `Strict-Transport-Security: max-age=63072000; includeSubDomains` in production.

## Consequences
- Single-instance deployments operate seamlessly with in-memory tracking.
- Horizontal scaling across multi-node clusters will require switching SlowAPI's storage backend to Redis (`REDIS_URL`).
