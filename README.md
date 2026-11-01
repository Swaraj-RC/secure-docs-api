# Secure Document & Records Management API

A production-grade, multi-tenant document and records management API built with FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, and modern security practices.

## Problem Statement

Organizations need a secure, auditable system to manage sensitive documents across departments and external parties with fine-grained access control, version tracking, and compliance-ready audit trails. This API provides exactly that — without the bloat of AI/ML features or real-time collaboration, focusing instead on correctness, security, and operational reliability.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Clients                              │
│              (Swagger UI / Frontend / CLI)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Application                      │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌───────────┐   │
│  │ Auth    │  │ Policies │  │ Services   │  │ Storage   │   │
│  │ (JWT +  │  │ (RBAC +  │  │ (Business  │  │ (Local /  │   │
│  │ Refresh)│  │  ACL)    │  │  Logic)    │  │  S3)      │   │
│  └─────────┘  └──────────┘  └────────────┘  └───────────┘   │
│  ┌─────────────────────────────────────────────────────┐     │
│  │              Audit Service (append-only)            │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   PostgreSQL 16                             │
│  Users │ Workspaces │ Documents │ Versions │ Audit Logs     │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Multi-tenant workspaces** with role-based access control (owner, admin, member, viewer).
- **Document management** with versioning, soft delete, trigram search, and classification levels (`public`, `internal`, `confidential`, `restricted`).
- **Secure file handling** — magic-byte MIME detection, SHA-256 integrity check, size caps, and opaque UUID storage keys.
- **Controlled cross-tenant sharing** — per-document ACLs with query-time temporal expiry, never exceeding granter's held permissions.
- **JWT authentication** with rotating opaque refresh tokens (SHA-256 in DB) and replay attack detection with family revocation.
- **Append-only audit trail** — every document creation, modification, download, and permission change logged immutably.
- **Security-first design** — Argon2id password hashing, consecutive failure account lockout, SlowAPI rate limiting, and HTTP security headers.
- **RFC 7807 error envelopes** with stable machine-readable codes and request ID tracing.

## Quickstart

```bash
# Clone the repository
git clone https://github.com/Swaraj-RC/secure-docs-api.git
cd secure-docs-api

# Start services
cp .env.example .env
docker compose up -d

# Open Swagger UI
# http://localhost:8000/docs

# Seed demo data
docker compose exec api python -m scripts.seed
```

## Environment Variables

See [`.env.example`](.env.example) for all configuration options. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `SECRET_KEY` | JWT signing secret key (must be changed in prod) | — |
| `ENVIRONMENT` | `development` / `production` | `development` |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `MAX_UPLOAD_SIZE_MB` | Maximum file upload size in megabytes | `25` |

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run full test suite with coverage
pytest --cov=app --cov-report=term-missing --cov-fail-under=85

# Lint and type check
ruff check app tests
ruff format --check app tests
mypy app tests
```

## Security

See [`docs/security.md`](docs/security.md) for the complete security model. Highlights:

- Argon2id password hashing configured with memory-hard parameters
- Short-lived JWT access tokens (15 min) + rotating refresh tokens (7 days)
- Refresh token reuse detection with family revocation
- Deny-by-default authorization with central pure policy module
- Leakage prevention rule (non-members receive 404 Not Found, never 403)
- File upload validation: size limits, MIME allowlist, magic-byte verification
- Downloads served with `Content-Disposition: attachment`, never inline
- Append-only audit log with foreign key cascade protection
- Security headers: HSTS, nosniff, DENY framing, no-referrer, CSP
- Rate limiting on auth and upload endpoints with Retry-After header

## Design Decisions

See [`docs/decisions/`](docs/decisions/) for Architecture Decision Records (ADRs):

- [ADR-0001: JWT Access & Refresh Token Rotation with Replay Detection](docs/decisions/ADR-0001-jwt-refresh-rotation.md)
- [ADR-0002: Deny-by-Default Central Authorization Policy](docs/decisions/ADR-0002-deny-by-default-authorization-policy.md)
- [ADR-0003: Document Search Strategy (GIN Trigram Indexing vs FTS)](docs/decisions/ADR-0003-document-search-strategy.md)
- [ADR-0004: Cross-Tenant Sharing Model & Leakage Prevention Rule](docs/decisions/ADR-0004-cross-tenant-sharing.md)
- [ADR-0005: Append-Only Audit Trail Architecture and Immutability Guarantees](docs/decisions/ADR-0005-append-only-audit-trail.md)
- [ADR-0006: Rate Limiting Strategy, Request Hardening, and HTTP Security Headers](docs/decisions/ADR-0006-rate-limiting-and-defense-in-depth.md)

## Build Log

See [`BUILD_LOG.md`](BUILD_LOG.md) — an engineering journal recording every real problem encountered during development and how it was resolved.

## License

MIT — see [LICENSE](LICENSE).
