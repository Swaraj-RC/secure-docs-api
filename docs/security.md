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
