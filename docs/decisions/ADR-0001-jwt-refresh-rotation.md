# ADR-0001: JWT Access Tokens with Rotating Refresh Tokens and Family Revocation

## Context

We need an authentication mechanism for a multi-tenant document management system that satisfies three requirements:
1. Low latency on authenticated requests (stateless verification where possible).
2. Ability to immediately revoke access upon credential theft or logout.
3. Protection against stolen refresh tokens being replayed.

## Decision

We implement a hybrid token architecture:
1. **Short-lived JWT access tokens** (15 minutes), signed using HMAC-SHA256 (`HS256`).
   - Claims: `sub` (user UUID), `jti` (random token UUID), `iat` (issued timestamp), `exp` (expiry timestamp).
   - No PII is included in the token payload.
2. **Rotating, opaque refresh tokens** (7-day validity):
   - The client receives a 256-bit cryptographically secure random hex string.
   - Only the SHA-256 hash (`token_hash`) is stored in PostgreSQL.
   - Each refresh token belongs to a `family_id` (UUID).
   - Upon rotation (`POST /auth/refresh`), the presented token is revoked, and a new token is created within the same family.
   - If an already-revoked refresh token is presented, the system detects replay/theft, revoking all active tokens sharing that `family_id` immediately.

## Consequences

- **Positive:** Compromised refresh tokens are limited in lifespan and detected automatically on replay. Access tokens require zero database round trips for signature verification.
- **Negative:** Access tokens cannot be revoked before their 15-minute expiration without maintaining a distributed deny-list. This trade-off is accepted in favor of reduced database load.
