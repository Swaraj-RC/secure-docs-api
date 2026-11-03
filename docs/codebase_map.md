# Codebase Map — A File-by-File Walkthrough of Secure Docs API

> **Welcome to the Engine Room.** 
> 
> When you open a professional backend repository for the first time, seeing dozens of files across `api/`, `core/`, `db/`, `schemas/`, and `services/` can feel overwhelming. 
> 
> This document is your **visual atlas**. It explains what every single folder and key file does in plain English, why it was created, and how they all connect together. No unexplained jargon. Just clear concepts and real-world analogies.

---

## Table of Contents
1. [The `app/` Directory (The Core Application)](#1-the-app-directory-the-core-application)
   - [`main.py` — The Front Entrance](#appmainpy--the-front-entrance)
   - [`core/` — The Central Nervous System](#appcore--the-central-nervous-system)
   - [`api/` — The Traffic Control & Routing](#appapi--the-traffic-control--routing)
   - [`db/` — The Database Connection & Tables](#appdb--the-database-connection--tables)
   - [`schemas/` — The Public API Contracts (Pydantic)](#appschemas--the-public-api-contracts-pydantic)
   - [`services/` — The Business Logic Coordinator](#appservices--the-business-logic-coordinator)
   - [`policies/` — The Security Bouncer (Access Rules)](#apppolicies--the-security-bouncer-access-rules)
   - [`storage/` — The Physical File Vault](#appstorage--the-physical-file-vault)
2. [The `tests/` Directory (The Safety Net)](#2-the-tests-directory-the-safety-net)
3. [The `alembic/` Directory (The Database's Time Machine)](#3-the-alembic-directory-the-databases-time-machine)
4. [The Root Files (Tooling & Infrastructure)](#4-the-root-files-tooling--infrastructure)
5. [The Request Lifecycle Map (End-to-End Trace)](#5-the-request-lifecycle-map)

---

## 1. The `app/` Directory (The Core Application)

This is where the actual backend code lives. Every line of code that executes when someone uses your API is inside this folder.

```
app/
├── main.py               # The application factory & server entry point
├── api/                  # HTTP routes, URL paths, dependency injection
├── core/                 # Shared configuration, security, errors, logging
├── db/                   # Database engine, connection session, ORM tables
├── policies/             # Pure access-control rules (authorization)
├── schemas/              # Pydantic data models (validation & serialization)
├── services/             # Business logic layer (orchestrates DB + storage)
└── storage/              # File handling drivers (local disk & AWS S3)
```

---

### `app/main.py` — The Front Entrance

* **What does it do?** It creates, configures, and returns the FastAPI application instance. It attaches global middleware (for security headers, request IDs, and file size checks) and registers all API routes.
* **Why does it exist?** Every web server needs a starting point. When you run `uvicorn app.main:app`, Uvicorn opens this file to find the `app` object.

#### Key Concepts in this File:
1. **What is an "App Factory"? (`create_app()`):**
   * *Analogy:* Ordering a custom car from an assembly plant rather than having one permanently welded to your garage floor.
   * Instead of creating a single global `app = FastAPI()`, we write a function `def create_app() -> FastAPI:`. This lets our test suite spin up clean, independent copies of the application with custom test settings without polluting each other.
2. **What does "Mounting Routers" mean? (`app.include_router(...)`):**
   * *Analogy:* An office building directory. The front lobby receptionist doesn't handle legal contracts, HR, and payroll personally; they direct you: *"For legal, take elevator A to Floor 4"* (`prefix="/api/v1"`).
   * Mounting means connecting groups of endpoints (like all document routes or all auth routes) to the main app under a shared URL prefix.

---

### `app/core/` — The Central Nervous System

This folder holds universal settings and utilities that every other part of the app relies on.

| File | What does it do? | Why does it exist? |
|---|---|---|
| **`config.py`** | Reads environment variables from the `.env` file (like `DATABASE_URL` and `SECRET_KEY`) into a strongly-typed Pydantic `Settings` class. | Hardcoding secrets (like passwords or tokens) in code is a dangerous security flaw. This file gives our app a single, safe place to read environment settings with default fallbacks. |
| **`security.py`** | Provides helper functions to hash passwords using **Argon2id**, verify passwords, and create/decode **JWT tokens** using `HS256`. | We never store raw passwords in plain text. This file isolates cryptographic math so the rest of the app doesn't have to worry about hashing algorithms. |
| **`errors.py`** | Defines our custom error types (`AppError`, `NotFoundError`, `ForbiddenError`) and global exception handlers that format every error into a clean **RFC 7807 JSON envelope** (`{"error": {"code": "...", "message": "..."}}`). | Without this, unhandled errors would return ugly HTML stack traces or inconsistent JSON formats. This guarantees clients always receive predictable error responses. |
| **`logging.py`** | Configures **structlog** to output structured JSON logs in production and colorful, readable logs in development. | In modern cloud environments (like AWS or Datadog), machines parse JSON logs to trigger alerts. This file ensures every log line includes timestamps and request tracing IDs. |
| **`rate_limit.py`**| Sets up the **SlowAPI** rate limiter instance. | Protects authentication and upload endpoints from brute-force bots and denial-of-service spam. |
| **`pagination.py`**| Defines generic pagination parameters (`page`, `size`) and the page container (`Page[T]`). | Users shouldn't fetch 100,000 documents in one giant HTTP request. This file standardizes pagination math across all list endpoints. |

---

### `app/api/` — The Traffic Control & Routing

This folder defines the HTTP URLs that clients can call.

```
app/api/
├── deps.py               # Dependency injection helpers (get_db, get_current_user)
└── v1/
    ├── router.py         # Merges all v1 sub-routers together
    └── endpoints/
        ├── auth.py       # POST /auth/login, /auth/refresh, /auth/register
        ├── documents.py  # GET, POST, DELETE /workspaces/{id}/documents
        ├── workspaces.py # CRUD for tenant workspaces and memberships
        ├── audit.py      # GET /workspaces/{id}/audit-logs (compliance history)
        └── health.py     # GET /healthz and /readyz (system monitoring)
```

#### What is `app/api/deps.py`?
* **Analogy:** The hotel concierge who checks your room key and hands you a freshly sanitized room key and Wi-Fi password.
* **What does it do?** It holds FastAPI "dependencies" like `get_db` (which yields an active database session and closes it when the request is done) and `get_current_user` (which reads the `Authorization: Bearer <token>` header, decodes it, and finds the user in the database).
* **Why does it exist?** Instead of writing 15 lines of token verification inside every single endpoint, we just write `current_user: User = Depends(get_current_user)`. FastAPI runs `deps.py` automatically.

---

### `app/db/` — The Database Connection & Tables

This folder manages how Python talks to PostgreSQL.

```
app/db/
├── base.py               # DeclarativeBase, UUIDMixin, TimestampMixin
├── session.py            # create_async_engine and session factory
└── models/               # SQLAlchemy ORM table definitions
    ├── user.py           # 'users' table
    ├── token.py          # 'refresh_tokens' table (token family tracking)
    ├── workspace.py      # 'workspaces' and 'workspace_members' tables
    ├── document.py       # 'documents' table (metadata)
    ├── version.py        # 'document_versions' table (immutable files)
    ├── share.py          # 'document_shares' table (cross-tenant access)
    └── audit.py          # 'audit_logs' table (compliance trail)
```

#### Key Concept: What is the difference between a Model and a Schema?
* **Database Model (`app/db/models/`):** 
  * Defines how data is stored inside **PostgreSQL tables** (columns, foreign keys, database indexes). 
  * Created using **SQLAlchemy** (`Mapped[str] = mapped_column(...)`).
  * Example: `User` model contains `password_hash` and internal database primary keys.
* **Pydantic Schema (`app/schemas/`):** 
  * Defines what data enters or leaves through the **public HTTP API** (JSON request bodies and JSON responses).
  * Created using **Pydantic** (`class UserResponse(BaseModel):`).
  * Example: `UserResponse` exposes `email` and `full_name`, but **hides** `password_hash` so secrets never leak to the frontend!

---

### `app/schemas/` — The Public API Contracts (Pydantic)

* **What does it do?** Defines the exact shape of JSON data accepted from clients and returned to clients.
* **Why does it exist?** If a user sends a number where a string was expected, or forgets a required field, Pydantic immediately catches it and returns a clean `422 Unprocessable Entity` error before any business code or database runs.

---

### `app/services/` — The Business Logic Coordinator

This folder contains the brain of the application.

```
app/services/
├── auth_service.py       # Login, token rotation, theft detection, lockout
├── document_service.py   # Document creation, upload ingestion, soft-delete
├── download_service.py   # Streaming file bytes, range requests, disposition headers
├── workspace_service.py  # Workspace creation, tenant membership management
├── share_service.py      # Cross-tenant document grants and expiration
├── audit_service.py      # Append-only audit logging helper
└── file_validation.py    # Magic bytes detection and MIME whitelisting
```

#### What is the "Service Layer" Pattern?
* **Analogy:** The Head Chef in a restaurant kitchen.
  * The waiter (the **API endpoint**) takes the customer's order and passes the ticket to the kitchen.
  * The waiter doesn't cook the steak or butcher the beef; the Head Chef (the **Service**) coordinates the prep station, cooks the meal, and hands the finished plate back to the waiter.
* **Why keep logic in Services instead of Endpoints?**
  1. **Separation of Concerns:** The endpoint handles HTTP details (status codes, query params, headers). The service handles pure business rules (calculating versions, updating hashes, verifying tenant membership).
  2. **Reusability:** If you need to create a document from an API endpoint, a background worker script, or a CLI command, all three can call `document_service.create_document()` without copying code.

---

### `app/policies/` — The Security Bouncer (Access Rules)

* **File:** `app/policies/access.py`
* **What does it do?** Contains pure, side-effect-free boolean functions (like `can_view_document`, `can_delete_document`, `can_create_version`).
* **Why is this separated from everything else?**
  * When security rules are mixed directly into SQL queries or endpoint routes, permissions become messy and almost impossible to test thoroughly.
  * By isolating access rules into pure functions that take simple inputs (user role, document classification, share status) and return `True` or `False`, we can test every single permission edge case in milliseconds without touching a database.

---

### `app/storage/` — The Physical File Vault

* **Files:** `base.py`, `local.py`, `s3.py`.
* **What does it do?** Defines an abstract interface (`StorageBackend`) and concrete drivers to save and read raw file bytes.
  * `local.py`: Saves files to the local server hard drive (`storage/workspaces/...`).
  * `s3.py`: Saves files to an Amazon Web Services (AWS) S3 cloud bucket.
* **Why does it exist?** The rest of the app doesn't need to know where files physically live. It simply calls `storage.save(stream, key)`. We can switch from local disk to AWS S3 by changing one line in `.env`.

---

## 2. The `tests/` Directory (The Safety Net)

Our automated test suite proves the backend works reliably and catches bugs before they reach customers.

```
tests/
├── conftest.py           # Shared Pytest fixtures, test DB setup, compiler shims
├── factories.py          # Test data generators (creates fake users/workspaces)
├── unit/                 # Ultra-fast isolated tests (no real DB or network)
│   ├── test_access_policy.py    # Tests all 33 permission permutations
│   ├── test_config.py           # Tests settings validation & defaults
│   ├── test_meta_security.py    # Automated scan ensuring all routes require auth
│   └── test_storage_local.py    # Tests file disk writing & range reading
└── integration/          # Real-world end-to-end tests (real DB & HTTP client)
    ├── test_auth_endpoints.py   # Login, token rotation, reuse attacks
    ├── test_documents.py        # Document creation, search, listing
    ├── test_uploads.py          # Real multipart streaming uploads & magic bytes
    └── test_migrations.py       # Tests Alembic upgrade and downgrade cycles
```

### Key Testing Concepts:
1. **Unit Tests vs. Integration Tests:**
   * **Unit Tests (`tests/unit/`):** Test one isolated function in complete isolation. They run in memory with zero database queries. They execute in fractions of a second.
   * **Integration Tests (`tests/integration/`):** Spin up an HTTP client and test real interactions between the endpoint, service, database, and storage. They prove the entire machine works when assembled.
2. **What is `conftest.py` and `pytest.fixture`?**
   * *Analogy:* A stage crew for a theater play. Before each scene starts, the crew sets up the furniture (`@pytest.fixture` creates a fresh database session and test user). After the scene ends, the crew cleans the stage (`yield` tears down and deletes temporary data) so the next actor starts with a clean stage.

---

## 3. The `alembic/` Directory (The Database's Time Machine)

```
alembic/
├── env.py                # Migration engine script (connects to target database)
└── versions/             # Sequential migration files
    ├── 0001_create_users.py
    ├── 0002_create_refresh_tokens.py
    ├── 0003_create_workspaces.py
    ├── 0004_create_documents.py
    ├── 0005_create_versions.py
    ├── 0006_create_shares.py
    └── 0007_create_audit_logs.py
```

* **What does `env.py` do?** It is the entry point that Alembic executes when you run `alembic upgrade head`. It reads your database URL, imports all models from `app/db/models/`, and applies any unexecuted migration files.
* **Why are there numbered files in `versions/`?**
  * Just like Git commits have parents and children, database migrations must run in an exact sequence.
  * You cannot create the `documents` table (`0004`) before the `workspaces` table (`0003`) exists, because documents reference workspaces with a foreign key! The numbers guarantee that PostgreSQL builds tables in the correct order.

---

## 4. The Root Files (Tooling & Infrastructure)

These configuration files live at the top of the repository to configure your developer environment and build pipeline.

| File | What does it do in plain English? |
|---|---|
| **`pyproject.toml`** | The central configuration file for the modern Python ecosystem. It lists our project dependencies (FastAPI, SQLAlchemy, Pydantic) and configures our code linters (**Ruff**), static type checker (**Mypy**), and test runner (**Pytest**). |
| **`docker-compose.yml`** | In one sentence: A configuration file that launches both our application and a real PostgreSQL 16 database container together with a single `docker compose up` command. |
| **`Makefile`** | A shortcut menu for terminal commands. Instead of typing `python -m pytest tests/unit -v --tb=short`, developers can just type `make test`. |
| **`Dockerfile`** | A multi-stage recipe that packages our Python code into a lightweight, secure Linux container image ready to run in the cloud. |
| **`BUILD_LOG.md`** | An engineering journal documenting real bugs encountered during development, root cause investigations, and lessons learned. |
| **`.env`** | A private file storing local secrets and database credentials (never committed to public Git!). |

---

## 5. The Request Lifecycle Map

To see how all these files work together as a team, follow this numbered trace of a real request:

### Scenario: A user uploads a new version of an existing document
* **HTTP Call:** `POST /api/v1/workspaces/{ws_id}/documents/{doc_id}/versions`

```
1. Client sends request ───────► Hits app/main.py
                                 (Middleware checks Content-Length, assigns X-Request-ID)

2. Route dispatched ──────────► Hits app/api/v1/endpoints/documents.py
                                 (FastAPI matches the URL path)

3. Dependencies run ──────────► Calls app/api/deps.py
                                 - get_current_user: Decodes JWT, authenticates user
                                 - get_db: Opens an async database session

4. Input validation ──────────► Uses app/schemas/version.py
                                 (Validates form fields and file metadata)

5. Business logic ────────────► Calls app/services/document_service.py
                                 (Coordinates the entire upload process)

6. Authorization check ───────► Calls app/policies/access.py
                                 (Pure function confirms user role has 'write' permission)

7. File verification ─────────► Calls app/services/file_validation.py
                                 (Inspects first 2,048 bytes with libmagic to confirm true MIME type)

8. Physical file save ────────► Calls app/storage/local.py
                                 (Streams 64KB chunks to an opaque UUID key on disk, computes SHA-256)

9. Database commit ───────────► Uses app/db/models/version.py and audit.py
                                 - Inserts new DocumentVersion row
                                 - Updates Document.current_version_id
                                 - Writes an AuditLog entry
                                 (Commits all 3 changes in one atomic SQL transaction)

10. Output response ──────────► Serialized via app/schemas/version.py
                                 (Returns HTTP 201 Created with JSON metadata and security headers)
```

---

### Mentor's Final Tip for Your Interview:
> If an interviewer asks you: *"How is your codebase organized?"*, you can summarize this map in two sentences:
> 
> *"We follow a clean layered architecture: HTTP endpoints in `app/api/` handle routing and input validation, business logic is centralized in `app/services/`, and authorization rules are completely isolated into pure functions in `app/policies/`. Data models are cleanly separated between SQLAlchemy database representations in `app/db/` and Pydantic public API contracts in `app/schemas/`."*
