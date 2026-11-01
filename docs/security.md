# Security Architecture & Threat Model

## Threat Model & Mitigations

| Threat Category | Potential Attack Vector | Mitigation in Architecture |
|---|---|---|
| **Credential Stuffing & Brute Force** | Dictionary attacks on `/auth/login` | Argon2id memory-hard password hashing + Per-user consecutive failure lockout (5 attempts / 15-min lock) + SlowAPI IP rate limiting (10 req/min). |
| **Token Theft & Replay** | Intercepted refresh token reuse | Rotating refresh tokens: single-use opaque tokens. Presentation of an already-used refresh token triggers family revocation, invalidating all associated sessions immediately. |
| **Cross-Tenant Data Leakage** | Guessing UUIDs across tenant boundaries | *Leakage Prevention Rule*: callers with no tenant membership or active share receive `404 Not Found` rather than `403 Forbidden`, preventing resource existence probing. |
| **Malicious File Upload** | Executables masked with `.pdf` extension | Magic byte header sniffing via `libmagic` (`python-magic`); user-supplied file extensions and MIME headers are discarded. |
| **Path Traversal & Storage Exploits** | Files named `../../etc/passwd` | Storage keys are opaque randomly generated UUIDs (`uuid.uuid4()`); original user filenames are strictly isolated to database metadata columns. |
| **Unbounded Payload DoS** | Enormous file streaming exhausting server memory | Early `Content-Length` inspection middleware rejecting payloads > 100MB before body parsing + chunked streaming validation in 64KB buffers. |
| **Browser Attacks & MIME Confusions** | Clickjacking, XSS, content sniffing | HTTP headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'`, and HSTS in production. |
| **Audit Log Tampering** | Malicious deletion of audit logs | Append-only schema with zero update/delete API routes, foreign key constraints with `ON DELETE RESTRICT` on actors, and immutable chronological recording. |

## Authentication Architecture

### Password Storage: Argon2id
Passwords are hashed using `argon2-cffi` configured with RFC 9106 recommended parameters:
- Algorithm: Argon2id
- Time cost: 3 iterations
- Memory cost: 64 MB ($65,536$ KiB)
- Parallelism: 4 lanes

### Access & Refresh Token Lifecycle
1. **Access Tokens:** Short-lived (15 minutes), signed using HMAC-SHA256 (`HS256`). Contain `sub` (User UUID), `exp`, `iat`, and `jti`.
2. **Refresh Tokens:** High-entropy cryptographically secure tokens (`secrets.token_urlsafe(48)`). Stored exclusively as SHA-256 hashes (`token_hash`) in the database; raw tokens are never persisted.
3. **Rotation & Replay Detection:**
   - Every call to `POST /auth/refresh` issues a new token pair and revokes the submitted refresh token.
   - If an already-revoked refresh token is presented, the system detects a token theft replay attack and immediately revokes all refresh tokens issued to that user.

## Authorization & Policy Model

Access evaluation is strictly deny-by-default and evaluated using pure functions in `app/policies/access.py`:

```
Access Matrix:
Classification | Workspace Owner/Admin | Workspace Member | Workspace Viewer | Non-Member
---------------+-----------------------+------------------+------------------+------------
public         | Full (Read/Write)     | Read             | Read             | None (404)
internal       | Full (Read/Write)     | Read             | Read             | None (404)
confidential   | Full (Read/Write)     | Own only (or ACL)| None (or ACL)    | None (404)
restricted     | Full (Read/Write)     | Own only (or ACL)| None (or ACL)    | None (404)
```

- **Sharing Grants:** Document owners and workspace admins can grant `read` or `write` access. Regular members can only grant `read` access. Grantees cannot grant permissions greater than what they possess.


## OWASP API Security Top 10 (2023) Review

| Category | Vulnerability | Architecture Defense & Implementation |
|---|---|---|
| **API1:2023** | Broken Object Level Authorization (BOLA) | Every resource endpoint enforces pure `can_*` functions from `app/policies/access.py`. Cross-tenant probes yield 404 rather than 403 to prevent enumeration. |
| **API2:2023** | Broken Authentication | Argon2id memory-hard hashing, rotating single-use refresh tokens with family revocation on replay, consecutive failure lockout, and strict token expiration. |
| **API3:2023** | Broken Object Property Level Authorization | Separate strict Pydantic schemas for Request and Response models. Sensitive attributes (e.g. `password_hash`, internal storage paths) are never exposed. |
| **API4:2023** | Unrestricted Resource Consumption | Upload size capped at 25MB (configurable), request body inspection middleware blocks >100MB before body parsing, pagination capped at `page_size <= 100`, SlowAPI rate limiting (10 req/min on auth & uploads). |
| **API5:2023** | Broken Function Level Authorization (BFLA) | Role hierarchy strictly verified (`owner` > `admin` > `member` > `viewer`). Admin operations (e.g. workspace membership changes, document restoration) verify role before service invocation. |
| **API6:2023** | Unrestricted Access to Sensitive Business Flows | Token rotation invalidates previous tokens; file upload pipeline enforces streaming chunk inspection, magic-byte MIME detection, and SHA-256 integrity validation. |
| **API7:2023** | Server Side Request Forgery (SSRF) | Zero user-supplied URLs are fetched by the server. S3 storage uses IAM credentials or signed URLs directly with configured AWS endpoints. |
| **API8:2023** | Security Misconfiguration | Strict CORS policy, `DEBUG=False` in production, fail-fast production startup validation (rejecting default secrets), and comprehensive security headers (`nosniff`, `DENY`, `no-referrer`, `CSP`, `HSTS`). |
| **API9:2023** | Improper Inventory Management | Strict API versioning under `/api/v1`, OpenAPI schema dynamically generated from Pydantic types, deprecated routes retired cleanly. |
| **API10:2023** | Unsafe Consumption of APIs | The service does not consume untrusted third-party HTTP APIs. Downstream dependencies are restricted to PostgreSQL and optional S3/boto3. |
