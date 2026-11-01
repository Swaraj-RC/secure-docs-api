# Security Model

## Authentication

### Password Storage
- Argon2id with tuned cost parameters
- No password length cap below 64 characters
- Minimum 8 characters enforced

### JWT Access Tokens
- HS256 signed with `SECRET_KEY`
- 15-minute expiry
- Claims: `sub` (user ID), `jti` (unique ID), `iat` (issued at)
- No PII in claims
- Clock skew tolerance: 30 seconds

### Refresh Tokens
- 256-bit random, only SHA-256 hash stored
- Single-use: every refresh rotates the token
- Family-based reuse detection: if a used token is replayed, the entire family is revoked
- 7-day expiry

## Authorization

- Deny-by-default: every route has an explicit auth dependency
- RBAC: workspace roles (owner > admin > member > viewer)
- ACL: per-document shares (read/write) with optional expiry
- Classification gates: confidential/restricted docs require elevated access
- Leakage rule: non-members get 404, insufficient-permission members get 403

## File Security

- Upload: size limit → MIME allowlist → magic-byte verification → checksum → opaque key storage
- Download: authorize → stream by opaque key → `Content-Disposition: attachment` → `nosniff`
- No user filenames in storage paths
- Path traversal protection: null bytes, `../`, control characters stripped

## Infrastructure

- Security headers: HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- CORS: explicit origin allowlist from environment
- Rate limiting: auth endpoints, file uploads
- Account lockout: 5 failed attempts → 15 minute lockout
- Structured errors: never leak stack traces or SQL
- Secrets: environment variables only, fail-fast in production if missing
