# Secure Document & Records Management API

A production-grade, multi-tenant document management API built with FastAPI, PostgreSQL, and modern security practices.

## Problem Statement

Organizations need a secure, auditable system to manage documents across teams with fine-grained access control, version tracking, and compliance-ready audit trails. This API provides exactly that — without the bloat of AI/ML features or real-time collaboration, focusing instead on correctness, security, and operational reliability.

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

- **Multi-tenant workspaces** with role-based access control (owner, admin, member, viewer)
- **Document management** with versioning, soft delete, and classification levels
- **Secure file handling** — magic-byte validation, checksum verification, opaque storage keys
- **Fine-grained sharing** — per-document ACLs with expiry, never exceeding granter's permissions
- **JWT authentication** with rotating refresh tokens and replay detection
- **Append-only audit trail** — every mutation and download logged with actor, resource, and metadata
- **Security-first design** — Argon2id passwords, rate limiting, account lockout, security headers
- **RFC 7807 error responses** with stable error codes and request tracing

## Quickstart

```bash
# Clone the repository
git clone https://github.com/Swaraj-RC/secure-docs-api.git
cd secure-docs-api

# Start services
cp .env.example .env
docker compose up -d

# Wait for startup, then open Swagger UI
# http://localhost:8000/docs

# (Optional) Seed demo data
docker compose exec api python scripts/seed.py
```

## Environment Variables

See [`.env.example`](.env.example) for all configuration options. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `SECRET_KEY` | JWT signing key (change in prod!) | — |
| `ENVIRONMENT` | `development` / `production` | `development` |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `MAX_UPLOAD_SIZE_MB` | Maximum file upload size | `25` |

## API Summary

All endpoints under `/api/v1`. See [`docs/api.md`](docs/api.md) for full details.

| Group | Endpoints | Auth |
|-------|-----------|------|
| Health | `GET /healthz`, `GET /readyz` | No |
| Auth | `POST /auth/register,login,refresh,logout`, `GET /auth/me` | Varies |
| Users | `GET/PATCH /users/me`, `POST /users/me/password` | Yes |
| Workspaces | CRUD + member management | Yes |
| Documents | CRUD + filter/sort/paginate | Yes |
| Versions | Upload, list, download, delete | Yes |
| Shares | Create, list, revoke per-document | Yes |
| Audit | Query audit logs | Yes |

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
make test

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# Check coverage (85% gate enforced)
pytest --cov=app --cov-report=html
```

## Security

See [`docs/security.md`](docs/security.md) for the full security model. Highlights:

- Argon2id password hashing with tuned cost parameters
- Short-lived JWT access tokens (15 min) + rotating refresh tokens
- Refresh token reuse detection with family revocation
- Deny-by-default authorization with central policy module
- File upload validation: size limits, MIME allowlist, magic-byte verification
- Downloads served with `Content-Disposition: attachment`, never inline
- Append-only audit log (DB role cannot UPDATE/DELETE)
- Security headers: HSTS, nosniff, DENY framing, no-referrer
- Rate limiting on auth and upload endpoints
- Account lockout after failed login attempts

## Design Decisions

See [`docs/decisions/`](docs/decisions/) for Architecture Decision Records (ADRs):

- ADR-0001: JWT + Refresh Token Rotation
- ADR-0002: Storage Abstraction Interface
- ADR-0003: Deny-by-Default Authorization

## Known Limitations

- No email delivery — password reset tokens logged to console
- No antivirus scanning — hook stub provided, not implemented
- S3 storage not included in default docker-compose
- No full-text semantic search
- No real-time collaboration
- No AI/ML features (by design)

## Build Log

See [`BUILD_LOG.md`](BUILD_LOG.md) — a chronological record of every real problem encountered during development and how it was resolved.

## License

MIT — see [LICENSE](LICENSE).
