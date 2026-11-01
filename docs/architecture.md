# System Architecture

## Overview
The Secure Document & Records Management API is built on FastAPI (async), SQLAlchemy 2.0 (async typed), PostgreSQL 16, and Alembic. It provides strict multi-tenant isolation, cryptographic audit logging, temporal resource access control, and defense-in-depth file pipelines.

```
+-----------------------------------------------------------------------+
|                             HTTP Client                               |
+-----------------------------------------------------------------------+
                                   |  (Bearer JWT / Request ID / CSP)
                                   v
+-----------------------------------------------------------------------+
|                    FastAPI Middleware Stack                           |
|  - Request ID Injection & Propagation                                 |
|  - Security Headers (nosniff, DENY, CSP, Permissions-Policy, HSTS)    |
|  - Content-Length Early Guard (413 Payload Too Large)                 |
|  - SlowAPI Rate Limiting (IP Token Bucket)                            |
|  - CORS & Global RFC 7807 Exception Handlers                          |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                       API Routing Layer (v1)                          |
|  - /auth           (Registration, Login, Rotating Refresh, Logout)    |
|  - /workspaces     (Tenants, Role-Based Memberships)                  |
|  - /documents      (CRUD, Soft Delete, Trigram/Filter Search)         |
|  - /versions       (Streaming Magic-Byte Upload, Range Downloads)     |
|  - /shares         (Cross-Tenant Explicit ACL Grants)                 |
|  - /audit-logs     (Workspace & Personal Append-Only Records)         |
+-----------------------------------------------------------------------+
        |                                    |
        v                                    v
+--------------------+            +------------------------------------+
|   Policy Engine    |            |           Service Layer            |
| (Pure Functional)  |            | - auth_service                     |
| - can_view_doc     |            | - workspace_service                |
| - can_edit_doc     |            | - document_service                 |
| - can_grant_share  |            | - share_service                    |
| - Leakage Rule     |            | - audit_service                    |
+--------------------+            +------------------------------------+
                                             |              |
                    +------------------------+              +---------+
                    v                                                 v
+--------------------------------------+            +-----------------------+
|      SQLAlchemy 2.0 Async ORM        |            |   Storage Backend     |
| - PostgreSQL 16 Dialect Engine       |            |   (StorageBackend)    |
| - JSONB Metadata & Trigram Indexes   |            | - LocalStorage        |
| - Partial Indexes (Soft Deletes)     |            | - S3Storage (aioboto3)|
+--------------------------------------+            +-----------------------+
```

## Layered Design & Separation of Concerns

1. **API Endpoints (`app/api/v1/endpoints/`):**
   - Pure HTTP contract mapping.
   - Pydantic payload validation and schema serialization.
   - Dependency injection for authentication (`get_current_user`), database sessions (`get_db`), and storage backends (`get_storage`).
   - Translates domain responses to HTTP envelopes; contains zero direct SQL or business logic.

2. **Policy Module (`app/policies/access.py`):**
   - Pure, stateless decision functions (`can_view_document`, `can_edit_document`, `can_grant_share`, `can_view_audit_logs`).
   - Decoupled from database sessions and network calls for testability.
   - Enforces the *Leakage Prevention Rule*: non-members always receive 404 Not Found rather than 403 Forbidden to conceal resource existence.

3. **Service Layer (`app/services/`):**
   - Coordinates business transactions, database queries, and storage operations.
   - Enforces temporal validity on shares (`expires_at > now()`).
   - Dispatches synchronous in-transaction audit logging for compliance integrity.

4. **Storage Layer (`app/storage/`):**
   - Unified `StorageBackend` Protocol: `put(key, stream)`, `get(key, offset, length)`, `delete(key)`, `exists(key)`.
   - File validation stream pipeline (`process_streaming_upload`): inspects magic bytes via `python-magic`, validates maximum file size, computes SHA-256 digests in memory buffers, and assigns opaque UUID storage keys (`uuid4.ext`).

## Multi-Tenancy & Resource Isolation
- Workspaces serve as tenant boundaries.
- Membership roles: `owner`, `admin`, `member`, `viewer`.
- Cross-tenant access is explicitly mediated via `document_shares` table with `read` or `write` permissions and optional expiration timestamps. Grantees gain access strictly to the shared document and its versions without discovering other workspace assets.

## Append-Only Audit Trail
- Table `audit_logs` records every mutating operation across documents, versions, shares, and memberships.
- Columns: `id`, `workspace_id`, `actor_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `user_agent`, `metadata` (JSONB), and `created_at`.
- Schema guarantees append-only property: no `updated_at`, no update/delete methods exist, and `actor_id` has `ON DELETE RESTRICT` to preserve historical integrity.
