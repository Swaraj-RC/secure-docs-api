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

---


### 2026-11-01 ? Coverage drops under async SQLAlchemy greenlet execution
- **Area:** Testing / Test Coverage (pyproject.toml)
- **Symptom:** Total coverage dropped to 79.17% (failing 85% gate) with large blocks of auth_service.py and workspace_service.py reported missing despite integration tests hitting every endpoint.
- **Context:** Executing Day 4 workspace and membership integration tests using AsyncClient and async database sessions.
- **Investigation:** Verified tests were genuinely passing and hitting the endpoints. Traced execution: SQLAlchemy asyncio delegates dialect execution into greenlet worker threads. By default, coverage.py only traces the main thread.
- **Root cause:** Without explicit concurrency configuration, coverage.py silently ignores code running inside greenlet threads spawned by SQLAlchemy async engine.
- **Fix:** Added [tool.coverage.run] with concurrency = ["thread", "greenlet"] and branch = true in pyproject.toml.
- **Verification:** Re-running pytest showed measured coverage jump from 79.17% to 91.68% across all 34 passing tests.
- **Lesson:** Always configure concurrency = ["thread", "greenlet"] in coverage settings for any project using SQLAlchemy 2.0 asyncio.
- **If asked in an interview:** "SQLAlchemy's async engine coordinates with greenlet threads under the hood. Without concurrency = ['thread', 'greenlet'] declared in pyproject.toml, coverage.py ignores code executed inside those greenlets, causing false coverage drops."
- **Time cost:** ~10 min

---


### 2026-11-01 ? Route reflection meta-test identifies unprotected logout endpoint
- **Area:** Authorization / Route Security (tests/unit/test_meta_security.py)
- **Symptom:** Meta-test failed: AssertionError: SECURITY VIOLATION: Route '/api/v1/auth/logout' [POST] is not in the public allowlist and has no authentication dependency attached!
- **Context:** Executing Day 5 security meta-test that inspects all registered FastAPI route dependencies.
- **Investigation:** Examined app/api/v1/endpoints/auth.py. Although the logout endpoint revoked refresh tokens passed in the request body, it lacked an HTTP Bearer dependency.
- **Root cause:** The handler signature omitted current_user = Depends(get_current_user).
- **Fix:** Added current_user: User = Depends(get_current_user) to the logout endpoint and updated integration test fixtures to provide valid Bearer tokens.
- **Verification:** Meta-test confirmed 100% of non-public routes require authentication.
- **Lesson:** Writing an automated meta-test that inspects application routes at test time reliably catches unprotected endpoints before code reaches production.
- **If asked in an interview:** "We wrote a meta-test that reflects over pp.routes and validates that every non-public endpoint declares an explicit authentication dependency. It immediately caught that our logout route lacked a Bearer token dependency, guarding against accidental route exposure."
- **Time cost:** ~5 min

---

## Open Questions / Known Limitations

- [ ] `python-magic` requires `libmagic1` system package — Dockerfile installs it, but local dev on Windows uses `python-magic-bin`
- [ ] Rate limiting is in-memory (single instance only) — Redis backend needed for horizontal scaling
- [ ] No email delivery — will log tokens to console
- [ ] S3 storage implementation is Day 7; not tested in CI compose
- [ ] Antivirus hook is a stub interface

## What I'd Do Next With More Time

- Redis-backed rate limiting and session store
- Webhook notifications for document events
- Background job queue (Celery/ARQ) for virus scanning and thumbnail generation
- OpenTelemetry tracing integration
- Kubernetes deployment manifests
- Database read replicas for audit log queries
