# Architecture

## Overview

The Secure Docs API follows a layered architecture with strict dependency rules:

```
Endpoints (API layer) → Services (business logic) → Models (data layer)
         ↓                      ↓
    Policies (authZ)      Storage (files)
         ↓
    Audit Service (cross-cutting)
```

## Layers

### API Layer (`app/api/`)
- FastAPI route handlers
- Request/response validation via Pydantic schemas
- Dependency injection for auth, pagination, workspace context
- No business logic — delegates to services

### Service Layer (`app/services/`)
- Business logic and orchestration
- No FastAPI imports — pure Python, testable in isolation
- Calls policy layer for authorization decisions
- Calls audit service for logging mutations

### Policy Layer (`app/policies/`)
- Central authorization module
- Pure functions: `can_view_document(actor, doc, role, share) -> bool`
- Deny-by-default: if not explicitly permitted, denied
- Encodes the full permission matrix (role × classification × share × ownership)

### Data Layer (`app/db/`)
- SQLAlchemy 2.0 async ORM models
- Alembic migrations (reversible)
- Session management via FastAPI dependency

### Storage Layer (`app/storage/`)
- Protocol-based abstraction (`StorageBackend`)
- Implementations: `LocalStorage`, `S3Storage`
- Files stored under opaque UUID keys — never user filenames

## Key Design Principles

1. **Deny by default** — every route requires explicit auth
2. **No inline permission checks** — all authZ goes through `policies/access.py`
3. **Append-only audit** — DB role cannot UPDATE/DELETE audit_logs
4. **Opaque storage keys** — user filenames never touch the filesystem
5. **404 over 403** — non-members get 404 to prevent existence leakage
