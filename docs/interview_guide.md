# Secure Docs API — Senior Backend Engineering Study Guide & Interview Bible

> **Mentor's Note:** When interviewing for senior backend roles, interviewers are rarely testing if you know syntax; they are testing your **systems thinking**, your **threat models**, and your **taste in trade-offs**. 
>
> You built a multi-tenant, compliance-ready document vault with append-only versioning, fine-grained access policies, and defense-in-depth security. This guide gives you the exact mental models, vocabulary, and "war stories" to explain every architectural decision you made.

---

## Table of Contents
1. [The 30-Second Pitch](#section-1-the-30-second-pitch)
2. [The Core Architecture & Request Lifecycle](#section-2-the-core-architecture--request-lifecycle)
3. [Authentication & Authorization (The Centerpiece)](#section-3-authentication--authorization-the-centerpiece)
4. [Database Modeling & Migration Engineering](#section-4-database-modeling--migration-engineering)
5. [Secure File Handling & Storage Pipeline](#section-5-secure-file-handling--storage-pipeline)
6. [The "War Stories" (Debugging in Production & CI)](#section-6-the-war-stories-from-build_logmd)
7. [Rapid-Fire Senior Technical Q&A](#section-7-rapid-fire-qa)
8. [Production Gaps & What We'd Improve in v2](#section-8-what-would-you-improve)

---

## Section 1: The 30-Second Pitch

### For the Non-Technical Recruiter
> *"I built a multi-tenant Document & Records Management API designed for high-compliance enterprise environments like aerospace or healthcare. It allows organizations to store, version, and share sensitive files with granular role-based permissions and complete auditability.*
> 
> *Think of it as a secure enterprise Google Drive backend: every file version is cryptographically verified with SHA-256 hashes, every access is audited, and organizations are completely isolated so one company can never see or know about another company's records. I built it with modern Python, FastAPI, and PostgreSQL, backed by an automated CI pipeline with 100+ tests and over 91% code coverage."*

### For the Senior Technical Interviewer
> *"Secure Docs API is an asynchronous, multi-tenant document vault built on FastAPI, SQLAlchemy 2.0 async, and PostgreSQL 16. The core challenge was achieving strict multi-tenant isolation and B2B cross-tenant document sharing without security leaks.*
> 
> *Architecturally, I decoupled business authorization into a pure-function policy layer that evaluates tenant bounds, RBAC roles, document classifications, and temporal share grants with zero ORM coupling. Files are ingested through a streaming pipeline that validates magic bytes via libmagic, computes SHA-256 checksums on the fly, and writes to opaque UUID storage keys.*
> 
> *On the database side, we maintain an append-only version history with circular foreign key pointers to active revisions. Authentication uses short-lived JWTs with single-use refresh token family rotation to detect replay attacks. The test suite runs against real PostgreSQL 16 in CI, including automated migration downgrade/upgrade cycles and an architectural meta-test that validates route authorization via AST and runtime dependency reflection."*

---

## Section 2: The Core Architecture & Request Lifecycle

```
[ HTTP Request: multipart/form-data or JSON ]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  1. BaseHTTPMiddleware & Security Filter               │
│     - Injects/propagates X-Request-ID (tracing)        │
│     - Enforces payload size guard (Content-Length)     │
│     - Attaches security headers (CSP, HSTS, nosniff)   │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  2. Routing & FastAPI Dependency Injection Container   │
│     - SlowAPI Rate Limiter check (in-memory / IP)      │
│     - Auth Dependency: extracts Bearer JWT from header │
│     - Validates claims, user active state in DB        │
│     - DB Dependency: yields scoped AsyncSession (ACID) │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  3. Pydantic v2 Serialization & Schema Validation      │
│     - Validates request body, query params, headers    │
│     - Rejects malformed types with RFC 7807 422 envelope│
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  4. Service Layer (Business Logic Coordinator)         │
│     - Fetches entity by ID within tenant context       │
│     - Invokes Pure Policy: can_read / can_write        │
│     - Raises AppError (404/403) on violation           │
│     - Interacts with StorageBackend (disk / S3 stream) │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  5. SQLAlchemy 2.0 Async Session                       │
│     - Executes async queries via asyncpg driver        │
│     - Appends AuditLog entry in the same transaction   │
│     - session.commit() / auto-rollback on error        │
└──────────────────┬─────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│  6. Response Pipeline                                  │
│     - Pydantic models serialize to JSON response       │
│     - Content-Security-Policy & request headers merged │
│     - HTTP Status 200/201/204 to client                │
└────────────────────────────────────────────────────────┘
```

### The Life of an API Request (e.g., Uploading a New Document Version)
1. **Network & Ingress (`app/main.py`):**
   The client issues `POST /api/v1/workspaces/{ws_id}/documents/{doc_id}/versions`.
   The `request_middleware` assigns a unique `X-Request-ID` via `structlog` and checks the incoming `Content-Length`. If the payload exceeds 100MB for versions (or 10MB for metadata routes), it short-circuits immediately with HTTP `413 Payload Too Large` before buffering memory.
2. **Dependency Injection & Authentication (`app/api/deps.py`):**
   FastAPI resolves route dependencies:
   - `get_db`: Yields an `AsyncSession` bound to PostgreSQL.
   - `get_current_user`: Extracts the Bearer token, decodes the HS256 JWT, checks expiration, and retrieves the active `User` model from the database.
   - `limiter`: SlowAPI verifies the client IP hasn't exceeded the endpoint rate limit (e.g., 10 req/min for uploads).
3. **Pydantic Validation:**
   The multipart form fields and `UploadFile` stream are parsed and validated against `VersionCreateRequest`.
4. **Service Layer & Pure Policy Check (`app/services/document_service.py`):**
   The service queries the `Document` and the caller's `WorkspaceMember` role.
   It calls the pure function `can_create_version(actor_role, doc_status, is_shared_grantee)`. If false, it immediately raises an `AppError(status_code=403, code="FORBIDDEN")` without touching storage.
5. **Secure Storage Ingestion (`app/storage/`):**
   The stream reads the first 2048 bytes to verify real MIME type using `python-magic`. If valid, it generates an unguessable UUID storage key (`storage/workspaces/{ws_id}/{uuid}`) and streams the file to storage while simultaneously updating an in-memory SHA-256 hash digest.
6. **Database Persistence & Audit Logging:**
   The `DocumentVersion` row is inserted, the `Document.current_version_id` is updated, and an `AuditLog` row is created—**all within the same database transaction**. If storage or DB fails, the session rolls back and orphaned files are cleaned up.
7. **Response Serialization:**
   FastAPI serializes the resulting ORM model to `DocumentVersionResponse` (filtering out internal storage paths) and sends HTTP 201 with tracing and security headers.

---

### Why this Tech Stack? What Were the Alternatives?

| Component | Choice | Alternatives Evaluated | Why We Picked It |
|---|---|---|---|
| **API Framework** | **FastAPI** | Django, Flask, Express/Node, Go Gin | High performance via Starlette/anyio async event loop; native Pydantic v2 validation; automatic OpenAPI documentation; built-in dependency injection for modular security. |
| **ORM / Data Access** | **SQLAlchemy 2.0 (Async)** | Tortoise ORM, Prisma Python, Peewee, raw SQL | True async DBAPI integration via `asyncpg`; 2.0 unified query syntax (`select(Model)`); rock-solid migration support via Alembic; handles complex joins, circular references, and partial indexes. |
| **Database** | **PostgreSQL 16** | MySQL, MongoDB, DynamoDB | `CITEXT` for case-insensitive uniqueness; `pg_trgm` GIN indexes for sub-millisecond search; native JSONB for structured audit metadata; true ACID isolation guarantees for compliance. |
| **Token Handling** | **Python-Jose / Argon2id** | PyJWT / bcrypt | Argon2id is the winner of the Password Hashing Competition (memory-hard, GPU/ASIC-resistant). Jose handles standardized JWT claims natively. |

---

## Section 3: Authentication & Authorization (The Centerpiece)

### 1. Dual-Token Architecture: JWT + Refresh Token Rotation

```
[ Client ]                        [ Secure Docs API ]                    [ Database ]
    │                                      │                                  │
    │  1. POST /auth/login (email/pwd)     │                                  │
    │─────────────────────────────────────>│ Verify Argon2id Hash             │
    │                                      │─────────────────────────────────>│
    │                                      │ Generate:                        │
    │                                      │ - Access Token (JWT, 15m)        │
    │  2. Return { access, refresh }       │ - Refresh Token (Opaque, 7d)     │
    │<─────────────────────────────────────│ Store token hash in refresh_tokens│
    │                                      │─────────────────────────────────>│
    │                                      │                                  │
    │  3. POST /auth/refresh (token)       │                                  │
    │─────────────────────────────────────>│ Query token by hash              │
    │                                      │─────────────────────────────────>│
    │                                      │ Check: revoked? expired?         │
    │                                      │ ──> IF ALREADY REVOKED:          │
    │                                      │     THEFT DETECTED!              │
    │                                      │     Revoke ENTIRE token family!  │
    │                                      │ ──> IF VALID:                    │
    │                                      │     Mark old token REVOKED       │
    │  4. Return NEW { access, refresh }   │     Issue NEW refresh token      │
    │<─────────────────────────────────────│─────────────────────────────────>│
```

#### Why Refresh Token Rotation is Non-Negotiable
- **Stateless Access Tokens (15 min):** Validated in-memory via cryptographic signature without hitting the database on every micro-request.
- **Stateful Refresh Tokens (7 days):** Stored in the database as SHA-256 hashes (`refresh_tokens` table).
- **Automatic Theft Detection (Family Invalidation):** Each refresh token is strictly **single-use**. When refreshed, the old token is marked `revoked = True` and replaced with a new token linked to the same `family_id`. 
  - If an attacker intercepts a refresh token and uses it *after* the legitimate client already refreshed, the server sees a revoked token presented. 
  - The API immediately detects token reuse and **revokes all active tokens in that entire family**, locking out the attacker instantly.

---

### 2. The Pure Policy Layer (`app/core/policies/access.py`)

Most junior codebases mix authorization checks into route handlers or ORM models:
```python
# ANTI-PATTERN (Tightly coupled, hard to test, error-prone)
@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: UUID, user: User = Depends(...)):
    doc = await db.get(Document, doc_id)
    if user.role != "admin" or doc.status == "archived":
        raise HTTPException(403)
```

#### Our Solution: Pure Functions & Structural Subtyping (Protocols)
We extracted every authorization rule into `app/core/policies/access.py` as **pure, side-effect-free functions**:
- They take simple Python objects or runtime `Protocol` interfaces (e.g., `DocumentAccessProtocol`).
- They contain **zero database queries** and **zero HTTP dependencies**.
- They return simple booleans: `True` or `False`.

```python
# SENIOR PATTERN: Pure, composable, testable in 1 millisecond
def can_delete_document(
    actor_role: WorkspaceRole | None,
    doc_status: DocStatus | str,
) -> bool:
    """Only workspace owners and admins can delete non-archived documents."""
    if actor_role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        return False
    return doc_status != DocStatus.ARCHIVED
```

**Why this wins in an interview:**
1. **Exhaustive Unit Testing:** We test 33 distinct permission edge cases (all matrix permutations of Owner, Admin, Member, Viewer, classification levels, and cross-tenant grants) without mocking a database or spinning up an HTTP server. Tests execute in **0.02 seconds**.
2. **Protocol Covariance:** By defining `@property` getters on our Protocols, our policy functions accept SQLAlchemy models, Pydantic schemas, or mock test dicts interchangeably without type errors.

---

### 3. The "404 vs 403 Leakage Rule" (Cross-Tenant Isolation)

> **Interview Golden Rule:** In a multi-tenant application, **existence is sensitive data**.

- **The Vulnerability (403 Leaking State):**
  Suppose Acme Aerospace is Workspace A, and Cyberdyne Systems is Workspace B.
  An attacker from Acme guesses a document UUID: `GET /workspaces/B/documents/{uuid}`.
  If the API returns **403 Forbidden**, the server has just confirmed to the attacker:
  *"That document exists, that workspace exists, and you just don't have the key."*
  Attackers use this response differentiation for UUID harvesting and tenant enumeration.

- **Our Defense (404 Concealment):**
  If a user has no membership in Workspace B, or if the document doesn't belong to their tenant, the service layer returns **404 Not Found**.
  To an unauthorized caller, **unauthorized resources are indistinguishable from non-existent resources**.
  We only return **403 Forbidden** if the user has verified access to the workspace/document context, but lacks the specific privilege for that action (e.g., a `Viewer` attempting to `DELETE` a file).

---

## Section 4: Database Modeling & Migration Engineering

```
┌─────────────────────────────────┐
│           workspaces            │
├─────────────────────────────────┤
│ id (UUID, PK)                   │
│ name (TEXT)                     │
│ slug (CITEXT, UNIQUE)           │
└───────────────┬─────────────────┘
                │ 1
                │
                │ *
┌───────────────▼─────────────────┐        1 ┌───────────────────────────────┐
│           documents             │◄─────────┤       document_shares         │
├─────────────────────────────────┤          ├───────────────────────────────┤
│ id (UUID, PK)                   │          │ id (UUID, PK)                 │
│ workspace_id (UUID, FK)         │          │ document_id (UUID, FK)        │
│ title (TEXT)                    │          │ user_id (UUID, FK)            │
│ current_version_id (UUID, FK)───┼──┐       │ permission ('read'/'write')   │
│ status ('draft'/'active'/...)   │  │       │ expires_at (TIMESTAMPTZ)      │
│ classification ('public'/...)   │  │       └───────────────────────────────┘
└───────────────▲─────────────────┘  │
                │ 1                  │
                │                    │
                │ *                  │
┌───────────────┴─────────────────┐  │
│        document_versions        │  │
├─────────────────────────────────┤  │
│ id (UUID, PK)                   │◄─┘  (Circular FK with deferred ALTER)
│ document_id (UUID, FK)          │
│ version_number (INT)            │
│ storage_key (TEXT, UNIQUE)      │
│ checksum_sha256 (CHAR(64))      │
│ size_bytes (BIGINT)             │
│ uploaded_by (UUID, FK)          │
│ created_at (TIMESTAMPTZ)        │
└─────────────────────────────────┘
```

### 1. Documents vs. Document Versions (Append-Only Immutability)
- **Why Separate Tables?** 
  In high-compliance audit systems, records are **append-only**. You never overwrite a file in place. 
  - `documents`: Holds mutable metadata (title, status, classification, workspace assignment).
  - `document_versions`: Immutable, write-once records representing physical file payloads.
- **Deduplication & Integrity:** Each version stores the exact `size_bytes` and `checksum_sha256`. A composite unique constraint `(document_id, version_number)` strictly prevents version collisions.

### 2. The `current_version_id` Circular Foreign Key
- **The Problem:** 
  To display a list of 50 documents with their file size and download link, querying the latest version via `SELECT ... WHERE version_number = MAX(...)` requires a costly `GROUP BY` subquery or window function across the entire versions table.
- **The Architectural Solution:** 
  `documents.current_version_id` caches a direct pointer to the active `document_versions.id`.
- **The Database Catch (Circular Dependency):**
  `documents` references `document_versions`, but `document_versions` references `documents`.
  Neither table can be created first with standard foreign keys!
- **How We Handled It in Alembic:**
  In migration `0004_documents`, `current_version_id` is created as a plain UUID column with no constraint.
  In migration `0005_versions`, `document_versions` is created referencing `documents.id`.
  Finally, `op.create_foreign_key("fk_current_version", ..., use_alter=True, ondelete="SET NULL")` alters the `documents` table to complete the circular link cleanly.

### 3. Why Alembic Over `Base.metadata.create_all()`?
`Base.metadata.create_all()` is acceptable only for hello-world prototypes. In real systems:
1. `create_all()` cannot migrate schemas over time—it only creates tables if they don't exist. It cannot add columns, rename constraints, or handle data migrations.
2. `create_all()` does not create PostgreSQL extensions (`citext`, `pg_trgm`).
3. It cannot handle circular foreign keys without complex manual event listeners.
4. In our CI pipeline, Alembic executes an automated **`upgrade head -> downgrade base -> upgrade head`** cycle. This mathematically proves that our database schema is 100% reversible and reproducible from scratch.

---

## Section 5: Secure File Handling & Storage Pipeline

```
[ User File Upload ] ──> HTTP Stream
                             │
                             ▼
              [ 1. Content-Length Header Guard ]
              Reject if > 100 MB immediately
                             │
                             ▼
              [ 2. Magic Bytes Inspection ]
              Buffer initial 2048 bytes
              Pass to libmagic / file(1)
              Reject if MIME not in whitelist (PDF, DOCX, PNG...)
                             │
                             ▼
              [ 3. Streaming Disk Write + SHA-256 ]
              Generate opaque UUID: storage/workspaces/{id}/{uuid}
              Stream chunks (64KB):
                ├── Write chunk to disk / S3
                └── Compute sha256_hash.update(chunk)
                             │
                             ▼
              [ 4. Atomic Transaction Commit ]
              Insert document_versions row (hash, size, key)
              Update document.current_version_id
              Write AuditLog entry
              COMMIT TRANSACTION
```

### 1. Why UUID Storage Keys Instead of Filenames?
If a user uploads `"Quarterly_Report.pdf"`, we save it on disk as `storage/workspaces/acme/f47ac10b-58cc-4372-a567-0e02b2c3d479`.
- **Path Traversal Elimination:** Attackers cannot upload `../../../../etc/shadow` or `..\Windows\System32\cmd.exe` to break out of the upload sandbox.
- **Collision Prevention:** Two users in the same company can upload a file named `notes.txt` without clobbering each other.
- **Encoding Safety:** Filenames with null bytes, emojis, or non-ASCII characters never touch the host filesystem driver. The original filename is stored safely in PostgreSQL and served back during download via RFC 6266 / RFC 5987 headers:
  ```http
  Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''Quarterly%20Report.pdf
  ```

### 2. Magic Byte Sniffing vs. Extension Spoofing
- **The Attack:** An attacker renames `malware.exe` to `invoice.pdf` and uploads it with `Content-Type: application/pdf`.
- **Our Defense:** We reject client-provided headers. We peek at the initial 2,048 bytes of the binary stream and evaluate the magic numbers via `python-magic` (`libmagic1`). If the actual binary signatures don't match our allowed MIME whitelist (`application/pdf`, `image/png`, etc.), the request is aborted with `415 Unsupported Media Type` before writing to disk.

---

## Section 6: The "War Stories" (From BUILD_LOG.md)

*Use the STAR method (Situation, Task, Action, Result) when discussing these in interviews.*

### War Story 1: The Silent CITEXT Dialect Divergence
- **Situation:** We needed email uniqueness to be strictly case-insensitive (`Jane@Corp.com` == `jane@corp.com`) to prevent account spoofing and credential confusion.
- **Task:** Support PostgreSQL's native `CITEXT` type in production while keeping local SQLite test fixtures blazing fast without requiring a running Docker daemon.
- **Action:** We implemented a SQLAlchemy `@compiles` compiler shim in `tests/conftest.py` that mapped `CITEXT` to `TEXT` for SQLite. However, during testing, we noticed SQLite was happily allowing `"user@test.com"` and `"User@Test.com"` to co-exist, while PostgreSQL would throw an `IntegrityError` in CI!
- **Root Cause:** A naive SQLite `TEXT` column uses binary collation (`BINARY`) by default.
- **Fix:** We updated the compiler shim to compile `CITEXT` specifically as `"TEXT COLLATE NOCASE"` on SQLite, aligning SQLite's uniqueness behavior with Postgres `CITEXT`. We then added an explicit regression test `test_user_email_case_insensitive_unique_constraint`.
- **Interview Pitch:** 
  > *"When writing cross-dialect test shims for speed, you have to verify semantic behavior, not just syntax. SQLite's default TEXT is case-sensitive, so our local tests allowed duplicate emails that would blow up on Postgres. Shimming to `TEXT COLLATE NOCASE` reconciled dialect behavior across both environments."*

---

### War Story 2: The Alembic `async_engine_from_config` Section Dict Trap
- **Situation:** In GitHub Actions CI, we spun up a `postgres:16-alpine` service container and ran our automated migration validation job (`alembic upgrade head -> downgrade base -> upgrade head`).
- **Task:** Ensure Alembic CLI uses the runtime `DATABASE_URL` environment variable pointing to the container.
- **Action:** Even though `alembic/env.py` resolved the URL and called `config.set_main_option("sqlalchemy.url", target_url)`, Alembic crashed in CI with a connection failure to `driver://user:pass@localhost/dbname`.
- **Root Cause:** In Alembic's async migration harness, `async_engine_from_config` takes `config.get_section(config.config_ini_section)`. That method returns a raw dictionary parsed directly from the static `alembic.ini` file! It completely ignores programmatic updates made to `set_main_option()`.
- **Fix:** In `alembic/env.py`, we explicitly copied the resolved URL into the dictionary copy: `section["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")` prior to passing it into `async_engine_from_config`.
- **Interview Pitch:** 
  > *"We uncovered a subtle disconnect in Alembic's async internals: `async_engine_from_config` reads directly from the raw parsed `alembic.ini` dictionary rather than the options registry. Copying the resolved option into the section dictionary ensured environment variables like `DATABASE_URL` are respected by async engines."*

---

### War Story 3: Circular FK Migration Failures in CI
- **Situation:** Our local test suite had initially bootstrapped the test database using SQLAlchemy's `Base.metadata.create_all`.
- **Task:** Move CI to real PostgreSQL 16 and test the complete Alembic migration lifecycle.
- **Action:** When CI executed `alembic upgrade head`, the database crashed on table creation.
- **Root Cause:** `create_all` had been quietly masking three production issues:
  1. It never executed our custom `CREATE EXTENSION citext` and `CREATE EXTENSION pg_trgm` statements.
  2. It created circular dependencies in unpredictable table order without the necessary `ALTER TABLE` deferrals.
  3. Alembic migrations had never actually been tested end-to-end against Postgres.
- **Fix:** We refactored `tests/conftest.py` so that Postgres test suites always bootstrap via `alembic command.upgrade(cfg, "head")`. We added a dedicated CI job that runs a full migration upgrade, downgrade to base, and re-upgrade.
- **Interview Pitch:** 
  > *"Relying on `create_all` in tests gives you a false sense of security because it bypasses extensions, custom enums, and circular foreign keys. Bootstrapping tests with Alembic migrations ensures your test suite runs against the exact DDL that runs in production."*

---

## Section 7: Rapid-Fire Q&A

**1. How do you handle database connection pooling in an async architecture?**
> *"We use SQLAlchemy's `AsyncAdaptedQueuePool` over `asyncpg`. We configure `pool_pre_ping=True` to eliminate stale connections, with a base `pool_size=10` and `max_overflow=20` to handle burst traffic without exhausting PostgreSQL's max connection limits."*

**2. What happens if a user requests a file version that was soft-deleted or archived?**
> *"Our service layer checks both the document and version status. If `doc.status == DocStatus.ARCHIVED`, the pure policy engine allows metadata reads to Admins and Owners for compliance auditing, but rejects all download streams with HTTP 403 or 404 depending on the caller's role."*

**3. Why did you choose Argon2id over bcrypt for password hashing?**
> *"Argon2id is the winner of the Password Hashing Competition and the current OWASP recommendation. Unlike bcrypt, which is vulnerable to GPU-accelerated cracking, Argon2id is memory-hard, making brute-force attacks on specialized hardware cost-prohibitive."*

**4. How do you prevent slowloris or denial-of-service file upload attacks?**
> *"We apply three layers of defense: First, our outermost middleware inspects the HTTP `Content-Length` header upfront and rejects oversized payloads before buffering. Second, file uploads are stream-processed in 64KB chunks rather than loaded into RAM. Third, SlowAPI limits upload attempts to 10 requests per minute per IP."*

**5. How do you ensure no developer accidentally exposes an unauthenticated endpoint?**
> *"We wrote an automated security meta-test (`test_meta_security.py`). It uses runtime reflection across FastAPI's route registry to verify that every single route—except those explicitly registered on our public allowlist—has an authentication dependency attached."*

**6. Why use HS256 for JWT instead of RS256 asymmetric keys?**
> *"Secure Docs API is currently deployed as a single unified service. HS256 symmetric signing is simpler and faster. If we scale to a distributed microservice topology where downstream services need to verify tokens without knowing the signing secret, we can seamlessly migrate to RS256 with public/private key pairs as documented in ADR-0001."*

**7. How do you prevent database deadlocks with circular foreign keys?**
> *"The circular FK between `documents` and `document_versions` uses `ondelete='SET NULL'` on the current version pointer and `use_alter=True`. Deletions cascade downward from document to versions while the foreign key is set to null, eliminating circular lock contention."*

**8. How do you handle file downloads safely without exhausting server memory?**
> *"We use FastAPI's `StreamingResponse` backed by an async generator that yields 64KB chunks directly from disk or S3. The entire file never resides in memory at any point during transmission."*

**9. How do you handle timezones across PostgreSQL and client APIs?**
> *"All database timestamp columns use `DateTime(timezone=True)` (TIMESTAMPTZ in Postgres), and Python normalization helpers force `datetime.now(UTC)`. All API responses format timestamps in ISO 8601 with explicit `Z` or `+00:00` offsets to prevent timezone ambiguity."*

**10. What is your strategy for cross-tenant sharing without data leakage?**
> *"Cross-tenant access is mediated through explicit `document_shares` records. When an external grantee queries a document, our query joins the share table, verifies `expires_at > now()`, and grants scoped access strictly to that single document ID without exposing workspace membership or metadata."*

---

## Section 8: What Would You Improve?

*Senior engineers know that all software engineering is a study in trade-offs. Here is the honest technical roadmap for v2:*

1. **Distributed Rate Limiting (Redis):**
   - *Current:* SlowAPI uses an in-memory dictionary.
   - *Improvement:* If we autoscale the API across multiple Kubernetes pods or containers, in-memory rate limits are partitioned. We would swap the storage backend to a Redis cluster (`REDIS_URL`) to share rate limit state across all replicas.
2. **Direct-to-S3 Presigned Uploads:**
   - *Current:* Files stream through the FastAPI application server to disk or S3.
   - *Improvement:* For files over 100MB, streaming through the web worker ties up Python async event loop threads. In v2, the client requests a presigned S3 upload URL, uploads directly to the object store, and triggers an S3 Event Notification or webhook to confirm ingestion.
3. **Transactional Outbox for Audit Logs:**
   - *Current:* Audit logs are written synchronously in the same SQL transaction as the business operation.
   - *Improvement:* While this guarantees ACID compliance, high-frequency audit writes increase write contention on the primary database. In v2, we would write audit events to an outbox table or Kafka queue to be asynchronously ingested into an append-only analytical store like ClickHouse.
4. **Antivirus Scanning Daemon:**
   - *Current:* The upload pipeline features an abstract `AntivirusScanner` interface with clean mocking.
   - *Improvement:* Connect the hook to a real ClamAV daemon (`clamd`) via Unix domain sockets to scan file buffers for malicious signatures prior to committing the transaction.

