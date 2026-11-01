# BUILD_LOG — Engineering Journal

Chronological record of problems encountered while building the Secure Document &
Records Management API, and how they were resolved. Each entry is specific enough
to reproduce the problem and the fix without seeing the commit.

**How to read:** Entries are grouped by date. Each entry documents a distinct problem
with symptom, investigation, root cause, fix, and verification. The "If asked in an
interview" section is a 2–3 sentence summary suitable for verbal explanation.

---

## Decisions Log (ADR-lite)

| Date | Decision | Alternatives Considered | Why |
|------|----------|------------------------|-----|
| 2026-11-01 | HS256 for JWT signing | RS256 (asymmetric) | Single-service deployment; HS256 is simpler, sufficient. RS256 adds key-pair management overhead with no benefit until we need multi-service token verification. Documented as reversible. |
| 2026-11-01 | structlog for logging | stdlib logging, loguru | Native async-friendly, structured JSON output, contextvar integration for request_id. stdlib is too verbose to configure; loguru lacks structured output control. |
| 2026-11-01 | SlowAPI for rate limiting | Custom middleware, redis-based | Lightweight, integrates with FastAPI natively. In-memory is fine for single-instance dev; documented Redis as production upgrade path. |
| 2026-11-01 | python-magic-bin on Windows, python-magic on Linux | pure-python alternatives | python-magic wraps libmagic (best MIME detection). Windows lacks libmagic natively; python-magic-bin bundles it. Conditional dependency in pyproject.toml. |
| 2026-11-01 | Multi-stage Docker build, non-root user | Single-stage | Smaller image (~200MB vs ~800MB), follows security best practices. Builder stage discarded after pip install. |
| 2026-11-01 | Deny-by-default centralized authorization policy | Distributed endpoint checks | Centralizes all RBAC and ACL logic in one pure-function module with zero ORM coupling, preventing data leakage. |
| 2026-11-01 | GIN pg_trgm index + ILIKE for document search | tsvector / tsquery, plain B-Tree | Fast substring matching for partial codes/vendor names without linguistic tokenization distortion; preserved SQLite test compatibility. |
| 2026-11-01 | Opaque UUID storage keys with original filename metadata | Content-addressed storage (SHA as key) | Shields filesystem from user-controlled paths, avoids collisions across re-uploads, and retains original filename for download headers. |
| 2026-11-01 | RFC 5987 / RFC 6266 dual Content-Disposition encoding | Bare ASCII filename | Preserves international UTF-8 filenames in modern browsers via filename*= while supplying sanitized ASCII fallback for legacy HTTP clients. |
| 2026-11-01 | Storage-level offset/length streaming for byte-range requests | In-memory slicing | Prevents loading multi-megabyte files into RAM; seeks file pointer directly on disk or S3 byte range. |
| 2026-11-01 | Controlled cross-tenant document sharing with least-privilege scoping | Strict intra-workspace sharing only | Permits external B2B collaboration/auditing for designated records without granting visibility into workspace tenant membership or other documents (ADR-0004). |

---

## Entries

### 2026-11-01 — Hatchling build backend cannot detect project package
- **Area:** Packaging / Build tooling (`pyproject.toml`)
- **Symptom:** `pip install -e ".[dev]"` failed with `ValueError: Unable to determine which files to ship inside the wheel using the following heuristics... no directory that matches the name of your project (secure_docs_api)`.
- **Context:** Setting up standard editable installation for local development with hatchling build backend.
- **Investigation:** Examined pip build error output. Hatchling defaults to looking for a directory named `src/secure_docs_api` or `secure_docs_api`. Because our source directory is named `app/`, hatchling's default heuristic failed.
- **Root cause:** Project name in `[project]` is `secure-docs-api`, but the application package directory is `app`. Without explicit package configuration, hatchling cannot guess the target.
- **Fix:** Added `[tool.hatch.build.targets.wheel]` with `packages = ["app"]` to `pyproject.toml`.
- **Verification:** Re-ran `pip install -e ".[dev]"`; editable package built and installed cleanly.
- **Lesson:** When using modern pyproject.toml build backends (Hatchling, Flit) with non-standard directory layouts (like top-level `app/`), always explicitly declare wheel package targets.
- **If asked in an interview:** "Hatchling expects the root directory to match the distribution name (`secure_docs_api`). Since our code lived in `app/`, editable install failed until we explicitly mapped `packages = ['app']` in the wheel target table."
- **Time cost:** ~5 min

### 2026-11-01 — PageParams default evaluation in unit tests
- **Area:** FastAPI dependency injection / Pagination
- **Symptom:** `test_page_params_defaults` failed: `assert params.page == 1` got `AssertionError: assert Query(1) == 1`.
- **Context:** Testing pagination parameter calculations and offset math in pure unit tests without HTTP requests.
- **Investigation:** `PageParams.__init__` had `page: int = Query(default=1, ...)` as default argument. When instantiated directly via `PageParams()`, Python assigns the default value expression (the `params.Query` instance) to `self.page` rather than the integer `1`.
- **Root cause:** FastAPI's `Query` marker is a default value placeholder for the DI container; outside of FastAPI's request evaluation pipeline, direct instantiation evaluates the `Query` object itself.
- **Fix:** Added `self.page = page.default if hasattr(page, "default") else page` and same for `size`.
- **Verification:** Unit tests passing for both default `PageParams()` instantiation and custom `PageParams(page=3, size=15)` calls.
- **Lesson:** When designing reusable class-based dependencies in FastAPI, ensure their constructors support both runtime DI injection and direct programmatic instantiation for unit testing.
- **If asked in an interview:** "Class-based FastAPI dependencies using `Query(default=...)` hold the `Query` metadata object when called directly in unit tests. Checking `hasattr(val, 'default')` allows class dependencies to be tested cleanly in unit isolation without spinning up FastAPI."
- **Time cost:** ~5 min

### 2026-11-01 — Starlette 404 bypasses custom RFC 7807 error envelope
- **Area:** Error handling / Starlette exceptions
- **Symptom:** `test_404_error_envelope` failed: response returned `{"detail": "Not Found"}` instead of our structured `{"error": {"code": "NOT_FOUND", ...}}`.
- **Context:** Verifying that unmatched routes conform to the strict RFC 7807 error envelope contract.
- **Investigation:** Examined exception handler registrations in `app/core/errors.py`. We registered handlers for `AppError`, `RequestValidationError`, and `Exception`. When a request hits an unmatched path, Starlette raises `starlette.exceptions.HTTPException(404)` inside routing, which Starlette catches internally before it reaches the global `Exception` handler.
- **Root cause:** Starlette's built-in `HTTPException` has default priority in FastAPI unless explicitly overridden by registering a handler for `starlette.exceptions.HTTPException`.
- **Fix:** Registered an explicit exception handler for `StarletteHTTPException` that maps status codes (404, 403, 401, 405) into the standard `_build_error_body` envelope.
- **Verification:** `GET /api/v1/nonexistent-route` returns 404 with standard `{error: {code: 'NOT_FOUND', ...}}`.
- **Lesson:** To guarantee 100% envelope compliance for client errors, always register a handler for `StarletteHTTPException` in addition to FastAPI's `RequestValidationError` and domain `AppError`.
- **If asked in an interview:** "FastAPI routes unhandled 404s via Starlette's internal `HTTPException`, returning standard `{detail: 'Not Found'}`. To enforce an RFC 7807 contract across all routes, you must explicitly register a handler for `starlette.exceptions.HTTPException`."
- **Time cost:** ~10 min

### 2026-11-01 — structlog AttributeError with PrintLoggerFactory
- **Area:** Structured logging (`structlog`)
- **Symptom:** `test_custom_exception_handlers` failed with `AttributeError: 'PrintLogger' object has no attribute 'name'` originating from `structlog.stdlib.add_logger_name`.
- **Context:** Logging unhandled 500 exceptions with `logger.exception("unhandled_error", ...)`.
- **Investigation:** Traced processor pipeline in `setup_logging`. `shared_processors` included `structlog.stdlib.add_logger_name`, which expects `logger.name` to exist on the underlying logger. When `PrintLoggerFactory` is used as the logger factory, `PrintLogger` instances do not have a `.name` attribute.
- **Root cause:** Mixing `structlog.stdlib` processors that expect Python stdlib `logging.Logger` objects with non-stdlib logger factories (`PrintLoggerFactory`).
- **Fix:** Removed `structlog.stdlib.add_logger_name` from `shared_processors`.
- **Verification:** Full logging pipeline functions without error for both JSON and console renderers on exception formatting.
- **Lesson:** When configuring structlog pipelines, ensure all processors in the chain match the logger factory type (stdlib vs print vs custom).
- **If asked in an interview:** "`add_logger_name` is an stdlib-specific processor that accesses `logger.name`. When using structlog's high-performance `PrintLoggerFactory`, that attribute doesn't exist. Processors must be matched to the logger factory backend."
- **Time cost:** ~5 min

### 2026-11-01 — 500 exceptions in BaseHTTPMiddleware and security header preservation
- **Area:** Middleware / Error handling
- **Symptom:** Unhandled exceptions in endpoint handlers raised `ExceptionGroup` or `RuntimeError` through `request_middleware`, bypassing header injection.
- **Context:** Testing that unexpected server errors (500) still return standard security headers (`X-Request-ID`, `X-Content-Type-Options: nosniff`).
- **Investigation:** In FastAPI / Starlette, `BaseHTTPMiddleware` wraps request processing. If an unhandled exception bubbles out of `call_next(request)`, it bypasses any response modification code after `call_next`. In test environments where `DEBUG=True`, Starlette's outer `ServerErrorMiddleware` re-raises the exception.
- **Root cause:** Lack of error handling inside `request_middleware` meant exceptions aborted middleware before security headers and request ID could be attached to the response.
- **Fix:** Wrapped `await call_next(request)` in a `try...except Exception` block in `request_middleware`, calling `_unhandled_error_handler` to generate a 500 response while continuing through the header injection pipeline.
- **Verification:** In `test_custom_exception_handlers`, 500 errors return proper RFC 7807 envelope with status 500, `X-Request-ID`, and all security headers attached.
- **Lesson:** Always handle unhandled exceptions inside the outermost middleware to ensure cross-cutting response headers (tracing, security) are never dropped during unexpected server errors.
- **If asked in an interview:** "If an endpoint throws an unhandled exception, it aborts `BaseHTTPMiddleware` execution before post-processing. Catching it in the middleware and returning the standard 500 error response guarantees security headers and request IDs are attached to every single HTTP response, even crashed ones."
- **Time cost:** ~10 min

### 2026-11-01 — PostgreSQL dialect shims for local SQLite test runner
- **Area:** Database / Testing (`sqlalchemy` + `tests/conftest.py`)
- **Symptom:** `CompileError: (sqlite) Don't know how to compile type CITEXT / UUID` when attempting to run async database integration tests locally without an active Docker daemon.
- **Context:** Implementing Day 2 User model using PostgreSQL-native types (`CITEXT`, `UUID`) while maintaining fast developer test execution without mandatory Docker service startup.
- **Investigation:** Explored running `testcontainers[postgres]`, which failed because the local Windows Docker pipe was not accessible (`FileNotFoundError: \\.\pipe\docker_engine`). SQLite doesn't natively support PostgreSQL extension types like `CITEXT`, `UUID`, `INET`, or `JSONB`.
- **Root cause:** SQLAlchemy's SQLite dialect compiler aborts on encountering PostgreSQL-specific dialect types during DDL execution (`Base.metadata.create_all`).
- **Fix:** In `tests/conftest.py`, registered SQLAlchemy `@compiles` shims for `CITEXT` -> `TEXT`, `UUID` -> `CHAR(36)`, `JSONB` -> `TEXT`, and `INET` -> `VARCHAR(45)` under SQLite, while falling back to `sqlite+aiosqlite:///:memory:` when `DATABASE_URL` is unset.
- **Verification:** Both PostgreSQL model definitions and integration tests pass without error locally on in-memory SQLite and against real PostgreSQL in CI.
- **Lesson:** Use dialect compilation overrides in test configuration to keep tests self-contained and runnable offline without sacrificing database-native types in production schema models.
- **If asked in an interview:** "We use PostgreSQL-specific types like CITEXT for case-insensitive uniqueness and UUID for keys. To keep local test suites runnable in under a second without requiring a live Docker daemon, we registered SQLAlchemy compiler shims that map those types to SQLite primitives during test fixture initialization."
- **Time cost:** ~15 min

### 2026-11-01 — Offset-naive vs offset-aware datetime comparison across SQL dialects
- **Area:** Authentication / Database date handling (`app/services/auth_service.py`)
- **Symptom:** `test_login_invalid_credentials_and_lockout` and `test_refresh_token_rotation_and_reuse_detection` failed with `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **Context:** Comparing `user.locked_until` and `token_record.expires_at` loaded from database against `now = datetime.now(UTC)`.
- **Investigation:** Examined traceback: the exception was raised directly on `user.locked_until > now`. While PostgreSQL returns timezone-aware datetimes for `TIMESTAMPTZ`, SQLite stores datetimes without timezone metadata and returns naive objects upon ORM deserialization.
- **Root cause:** Direct comparison between Python `datetime.now(UTC)` (aware) and ORM-deserialized datetimes from SQLite (naive) triggers a Python `TypeError`.
- **Fix:** Implemented `_to_utc(dt: datetime) -> datetime` in `app/services/auth_service.py` to ensure `dt.replace(tzinfo=UTC)` is called whenever `dt.tzinfo is None` prior to comparison.
- **Verification:** Both account lockout expiry and refresh token expiration tests run and pass without type errors.
- **Lesson:** Never compare `datetime.now(UTC)` directly with database datetime fields without normalizing `tzinfo`, as differing SQL dialects handle timestamp timezones differently.
- **If asked in an interview:** "SQLite drops timezone offsets on serialization, returning naive datetimes. Comparing `now(UTC)` with a naive datetime throws a `TypeError`. We normalized all timestamps with a helper that coerces naive values to UTC before any comparison."
- **Time cost:** ~10 min

### 2026-11-01 — Coverage drops under async SQLAlchemy greenlet execution
- **Area:** Testing / Test Coverage (`pyproject.toml`)
- **Symptom:** Total coverage dropped to 79.17% (failing 85% gate) with large blocks of `auth_service.py` and `workspace_service.py` reported missing despite integration tests hitting every endpoint.
- **Context:** Executing Day 4 workspace and membership integration tests using `AsyncClient` and async database sessions.
- **Investigation:** Verified tests were genuinely passing and hitting the endpoints. Traced execution: SQLAlchemy asyncio delegates dialect execution into greenlet worker threads. By default, coverage.py only traces the main thread.
- **Root cause:** Without explicit concurrency configuration, coverage.py silently ignores code running inside greenlet threads spawned by SQLAlchemy async engine.
- **Fix:** Added `[tool.coverage.run]` with `concurrency = ["thread", "greenlet"]` and `branch = true` in `pyproject.toml`.
- **Verification:** Re-running pytest showed measured coverage jump from 79.17% to 91.68% across all passing tests.
- **Lesson:** Always configure `concurrency = ["thread", "greenlet"]` in coverage settings for any project using SQLAlchemy 2.0 asyncio.
- **If asked in an interview:** "SQLAlchemy's async engine coordinates with greenlet threads under the hood. Without concurrency = ['thread', 'greenlet'] declared in pyproject.toml, coverage.py ignores code executed inside those greenlets, causing false coverage drops."
- **Time cost:** ~10 min

### 2026-11-01 — Route reflection meta-test identifies unprotected logout endpoint
- **Area:** Authorization / Route Security (`tests/unit/test_meta_security.py`)
- **Symptom:** Meta-test failed: `AssertionError: SECURITY VIOLATION: Route '/api/v1/auth/logout' [POST] is not in the public allowlist and has no authentication dependency attached!`.
- **Context:** Executing Day 5 security meta-test that inspects all registered FastAPI route dependencies.
- **Investigation:** Examined `app/api/v1/endpoints/auth.py`. Although the logout endpoint revoked refresh tokens passed in the request body, it lacked an HTTP Bearer dependency.
- **Root cause:** The handler signature omitted `current_user = Depends(get_current_user)`.
- **Fix:** Added `current_user: User = Depends(get_current_user)` to the logout endpoint and updated integration test fixtures to provide valid Bearer tokens.
- **Verification:** Meta-test confirmed 100% of non-public routes require authentication.
- **Lesson:** Writing an automated meta-test that inspects application routes at test time reliably catches unprotected endpoints before code reaches production.
- **If asked in an interview:** "We wrote a meta-test that reflects over `app.routes` and validates that every non-public endpoint declares an explicit authentication dependency. It immediately caught that our logout route lacked a Bearer token dependency, guarding against accidental route exposure."
- **Time cost:** ~5 min

### 2026-11-01 — PydanticSchemaGenerationError on generic Page[Document] with SQLAlchemy models
- **Area:** Schemas / Pagination (`app/core/pagination.py`)
- **Symptom:** `pydantic.errors.PydanticSchemaGenerationError: Unable to generate pydantic-core schema for <class 'app.db.models.document.Document'>`.
- **Context:** Type annotating service function return types with `Page[Document]`.
- **Investigation:** Traced Pydantic model evaluation in `app/services/document_service.py`. When `Page[Document]` is evaluated at import time, Pydantic attempts to build a schema for arbitrary SQLAlchemy models in `items: list[T]`.
- **Root cause:** `BaseModel` defaults to `arbitrary_types_allowed=False`, raising an exception when generic arguments are non-Pydantic ORM classes.
- **Fix:** Configured `model_config = ConfigDict(arbitrary_types_allowed=True)` on `Page[T]` in `app/core/pagination.py`.
- **Verification:** Service functions return `Page[Document]` cleanly and serializing to `Page[DocumentResponse]` succeeds.
- **Lesson:** Generic envelope containers used across both service layers and API boundaries should enable `arbitrary_types_allowed` to accommodate ORM entities.
- **If asked in an interview:** "Generic Pydantic models like `Page[T]` fail schema generation if parametrized with ORM model classes. Adding `arbitrary_types_allowed=True` to the generic model config permits typing service returns with database models before response mapping."
- **Time cost:** ~5 min

### 2026-11-01 — Protocol attribute invariance on StrEnum types in mypy
- **Area:** Type Safety / Protocols (`app/policies/access.py`)
- **Symptom:** `mypy app tests` failed with `Argument "doc" to "can_view_document" has incompatible type "Document"; expected "DocumentAccessProtocol" [arg-type]`. Following members have conflicts: `classification: expected "str", got "DocClassification"`.
- **Context:** Passing SQLAlchemy model instances with `StrEnum` attributes into pure policy functions accepting `DocumentAccessProtocol`.
- **Investigation:** `DocumentAccessProtocol` defined mutable instance attributes: `classification: str`, `status: str`. In Python typing, mutable protocol attributes are invariant: only exact `str` is accepted, not subtypes like `DocClassification(StrEnum)`.
- **Root cause:** Defining protocol attributes as simple variables rather than `@property` getters enforces strict type invariance.
- **Fix:** Changed protocol attributes to read-only property getters (`@property def classification(self) -> str: ...`).
- **Verification:** mypy passed with zero errors across all source files.
- **Lesson:** In typing protocols, always define read-only attributes using `@property` to allow subtype covariance.
- **If asked in an interview:** "Plain attribute annotations on a `Protocol` are invariant in Python typing, so a subclass like `StrEnum` won't satisfy a `str` attribute. Defining `@property` on the protocol makes the attribute covariant and read-only, matching enum subclasses smoothly."
- **Time cost:** ~5 min

### 2026-11-01 — Monkeypatching Pydantic Settings property on singleton instance
- **Area:** Testing / Configuration (`tests/integration/test_uploads.py`)
- **Symptom:** `AttributeError: property 'max_upload_size_bytes' of 'Settings' object has no setter` during pytest monkeypatching.
- **Context:** Overriding maximum allowed file upload size in unit test to verify oversized file rejection without allocating 25MB payloads.
- **Investigation:** `settings` is an instantiated singleton of `Settings`. In Python, an instance attribute assigned over a class property descriptor fails if the property has no setter. Furthermore, mutating `MAX_UPLOAD_SIZE_MB = 0` persisted into subsequent test runs on the cached singleton.
- **Root cause:** Attempting to assign directly to a read-only property on an instance rather than patching the property descriptor on the class definition.
- **Fix:** Used `monkeypatch.setattr(Settings, "max_upload_size_bytes", property(lambda self: 100))` on the `Settings` class, ensuring automatic teardown restoration.
- **Verification:** `test_oversized_file_rejected` passes and resets clean state for all subsequent test cases.
- **Lesson:** When overriding computed property descriptors in tests, patch the descriptor on the target class rather than the instance to allow clean setterless overriding and automatic restoration.
- **If asked in an interview:** "Pydantic properties without setters cannot be patched directly on the instance object. Patching the property descriptor on the class with `monkeypatch.setattr(Settings, ...)` cleanly mocks the dynamic property and restores it after test execution."
- **Time cost:** ~5 min

### 2026-11-01 — Module namespace isolation for optional aioboto3 dependency
- **Area:** Storage / Dependency Management (`app/storage/s3.py`)
- **Symptom:** `NameError: name 'aioboto3' is not defined` when mocking optional S3 backend without `aioboto3` installed on the host.
- **Context:** Writing unit tests for `S3Storage` to achieve high branch coverage on environments where AWS SDK is not locally installed.
- **Investigation:** Top-level `try: import aioboto3 except ImportError:` did not bind `aioboto3` in module globals when the package was missing. When tests subsequently injected a mock into `sys.modules["aioboto3"]`, calling `aioboto3.Session()` failed because the global name was never created.
- **Root cause:** Failed top-level import leaves the variable unbound in module globals.
- **Fix:** Replaced optional import check with `importlib.util.find_spec("aioboto3") is not None` and deferred `import aioboto3` inside `S3Storage.__init__`.
- **Verification:** Unit tests with mocked `aioboto3` session execute full CRUD operations against `S3Storage` with 80% branch coverage.
- **Lesson:** For modules with optional third-party integrations, defer binding the library to the class constructor to support clean dependency injection and mocking.
- **If asked in an interview:** "If a top-level optional import fails, the variable is unbound in globals, causing NameErrors even if later mocked in `sys.modules`. Deferring `import aioboto3` inside the class constructor allows seamless mocking during test execution without installing heavyweight cloud SDKs."
- **Time cost:** ~5 min

### 2026-11-01 — Query-time temporal filtering for document shares
- **Area:** Authorization / Temporal Access (`app/services/share_service.py`)
- **Symptom:** Expired document shares remained queryable via `GET /documents/{doc_id}/shares` and required defensive checks at multiple service layers.
- **Context:** Enforcing that shares with `expires_at < now()` are immediately invalidated without requiring a background cron job.
- **Investigation:** Examined share lookup logic: shares with past expiration timestamps were stored in the database indefinitely until explicitly deleted or updated.
- **Root cause:** Omitting temporal filters from `list_shares` and `get_active_share` queries left expired shares visible to callers.
- **Fix:** Integrated SQL condition `or_(expires_at.is_(None), expires_at > now())` on share listings and validated `is_share_active(share)` across all access control hooks.
- **Verification:** `test_expired_shares_ignored_at_query_time` confirms expired shares immediately return 404 to grantees and are omitted from active share lists.
- **Lesson:** Always apply query-time temporal bounds to time-limited access tokens and grants so expiration takes effect instantaneously without reliance on periodic janitor jobs.
- **If asked in an interview:** "Instead of relying on a background worker to clean up expired rows, we filter `or_(expires_at.is_(None), expires_at > now())` at query time and evaluate timestamps in policy checks, ensuring instant, zero-latency access revocation."
- **Time cost:** ~5 min

---

## Open Questions / Known Limitations

- [ ] `python-magic` requires `libmagic1` system package — Dockerfile installs it, but local dev on Windows uses `python-magic-bin`
- [ ] Rate limiting is in-memory (single instance only) — Redis backend needed for horizontal scaling
- [ ] No email delivery — will log tokens to console
- [ ] S3 storage implementation tested with mocks, optional for cloud deployment
- [ ] Antivirus hook is a stub interface

## What I'd Do Next With More Time

- Redis-backed rate limiting and session store
- Webhook notifications for document events
- Background job queue (Celery/ARQ) for virus scanning and thumbnail generation
- OpenTelemetry tracing integration
- Kubernetes deployment manifests
- Database read replicas for audit log queries
