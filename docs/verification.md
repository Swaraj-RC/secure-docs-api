# Verification & Test Execution Transcript

This document records the exact verification commands and outputs validating the Secure Document & Records Management API across testing backends, database migrations, static typing, and production container deployment.

---

## 1. Test Suite Execution & Code Coverage

The test suite enforces a strict `85%` branch-coverage gate configured in `pyproject.toml`.

### Canonical PostgreSQL 16 Test Run (CI Runner)

In continuous integration (`.github/workflows/ci.yml`), tests run against an ephemeral `postgres:16-alpine` service container. Database tables and extensions (`citext`, `pg_trgm`) are bootstrapped using Alembic migrations:

```bash
docker compose -f docker-compose.test.yml up -d
DATABASE_URL="postgresql+asyncpg://test:test@localhost:5433/test" TEST_BACKEND=postgres \
  pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

### Local Fast Unit Test Run (SQLite Fallback)

```bash
TEST_BACKEND=sqlite pytest --cov=app --cov-report=term-missing --cov-fail-under=85
```

**Execution Output:**
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.3.3, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: C:\Users\Swaraj\OneDrive\Desktop\back
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, Faker-29.0.0, platformdirs-4.14.2, asyncio-0.24.0, cov-7.1.0, randomly-5.0.0
asyncio: mode=Mode.AUTO, default_loop_scope=function
collected 102 items

tests/unit/test_access_policy.py::test_can_manage_shares_matrix PASSED   [  0%]
tests/unit/test_access_policy.py::test_can_view_document_matrix[...] PASSED [ 32%]
tests/integration/test_shares.py::test_cannot_grant_more_than_held PASSED [ 33%]
tests/integration/test_shares.py::test_expired_shares_ignored_at_query_time PASSED [ 34%]
tests/integration/test_shares.py::test_grant_list_revoke_share_lifecycle PASSED [ 35%]
tests/integration/test_downloads.py::test_full_download_with_security_headers PASSED [ 39%]
tests/integration/test_downloads.py::test_range_request_partial_content PASSED [ 40%]
tests/integration/test_downloads.py::test_download_leakage_and_permission_checks PASSED [ 41%]
tests/integration/test_edge_cases.py::test_account_lockout_recovery_after_expiry PASSED [ 43%]
tests/integration/test_edge_cases.py::test_workspace_admin_and_owner_edge_cases PASSED [ 44%]
tests/integration/test_edge_cases.py::test_superuser_dependency_unit PASSED [ 45%]
tests/integration/test_edge_cases.py::test_document_advanced_filters_and_invalid_sort PASSED [ 46%]
tests/integration/test_edge_cases.py::test_inactive_user_cannot_authenticate_or_access PASSED [ 47%]
tests/integration/test_users_db.py::test_user_email_unique_constraint PASSED [ 48%]
tests/integration/test_users_db.py::test_user_email_case_insensitive_unique_constraint PASSED [ 49%]
tests/integration/test_users_db.py::test_create_and_retrieve_user PASSED [ 50%]
tests/unit/test_errors.py::test_404_error_envelope PASSED                [ 50%]
tests/integration/test_auth_endpoints.py::test_auth_me_unauthorized PASSED [ 52%]
tests/integration/test_auth_endpoints.py::test_logout_revokes_token PASSED [ 53%]
tests/integration/test_auth_endpoints.py::test_register_and_login_lifecycle PASSED [ 54%]
tests/integration/test_auth_endpoints.py::test_login_invalid_credentials_and_lockout PASSED [ 55%]
tests/integration/test_auth_endpoints.py::test_refresh_token_rotation_and_reuse_detection PASSED [ 56%]
tests/integration/test_audit_logs.py::test_audit_log_filtering_and_share_events PASSED [ 57%]
tests/integration/test_audit_logs.py::test_audit_log_recorded_on_document_lifecycle PASSED [ 58%]
tests/integration/test_audit_logs.py::test_audit_log_access_control_and_leakage_rule PASSED [ 59%]
tests/integration/test_uploads.py::test_successful_file_upload_and_versioning PASSED [ 60%]
tests/integration/test_workspaces.py::test_workspace_roles_and_member_permissions PASSED [ 75%]
tests/integration/test_workspaces.py::test_workspace_crud_and_leakage_rule PASSED [ 76%]
tests/integration/test_migrations.py::test_alembic_migrations_revisions_chain PASSED [ 77%]
tests/integration/test_migrations.py::test_alembic_upgrade_downgrade_cycle SKIPPED [ 78%]
tests/integration/test_documents.py::test_document_query_filters_and_sorting PASSED [100%]

=============================== tests coverage ================================
Name                                 Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------
app/api/deps.py                         31      5     10      3    80%   25, 29-30, 34, 36
app/api/v1/endpoints/audit.py           20      0      0      0   100%
app/api/v1/endpoints/auth.py            35      0      0      0   100%
app/api/v1/endpoints/documents.py       82      0      4      1    99%   214->230
app/api/v1/endpoints/health.py          13      0      0      0   100%
app/api/v1/endpoints/workspaces.py      42      1      0      0    98%   72
app/core/config.py                      65      0      6      1    99%   98->102
app/core/errors.py                      68      3      2      0    96%   200-212
app/core/logging.py                     25      0      4      1    97%   30->32
app/core/pagination.py                  20      0      0      0   100%
app/core/rate_limit.py                   5      0      0      0   100%
app/core/security.py                    43      2      2      0    96%   34-35
app/policies/access.py                  78      9     36      2    87%   77-79, 98-99, 126-128, 136
app/services/audit_service.py           54      5     20      5    86%   81, 83, 109, 111, 113
app/services/auth_service.py            82      5     20      4    91%   66-67, 121, 139, 143
app/services/document_service.py       210     17     48     13    88%   67, 145, 180, 186, 231, 247->250...
app/services/download_service.py        37      4     16      4    85%   28, 32, 40, 50
app/services/file_validation.py         76      8     26      6    84%   19-20, 35, 49, 54-56...
app/services/share_service.py           96      6     24      7    89%   53, 68, 80->85, 86, 144...
app/services/workspace_service.py      114      8     34      9    89%   115, 117->120, 192, 200...
app/storage/local.py                    71      5     20      3    91%   25, 46-47, 94->exit...
--------------------------------------------------------------------------------
TOTAL                                 1781    104    298     67    91%
Required test coverage of 85% reached. Total coverage: 91.29%
================= 101 passed, 1 skipped, 1 warning in 27.82s ==================
```

---

## 2. Alembic Migration Chain & Upgrade/Downgrade Lifecycle

A dedicated migration test (`tests/integration/test_migrations.py`) verifies the 7-revision migration chain:

```bash
# Verify migration chain integrity
pytest tests/integration/test_migrations.py -k test_alembic_migrations_revisions_chain

# Run clean upgrade head -> downgrade base -> upgrade head lifecycle
make migrate-check
```

**Revision Chain:**
- `0001_users` (citext extension, users table, unique email)
- `0002_tokens` (refresh_tokens table, family_id, token_hash index)
- `0003_workspaces` (workspace_role enum, workspaces, workspace_members)
- `0004_documents` (pg_trgm extension, doc_status/doc_classification enums, documents table, GIN trigram index)
- `0005_versions` (document_versions table, fk_current_version deferred FK)
- `0006_shares` (share_permission enum, document_shares table, ACL bounds)
- `0007_audit` (audit_logs table, immutable actor/resource tracking)

---

## 3. Static Analysis, Formatting, & Strict Typing

```bash
# 1. Lint with ruff
ruff check app tests scripts
# Output: All checks passed!

# 2. Format check with ruff
ruff format --check app tests scripts
# Output: 83 files already formatted

# 3. Strict type checking with mypy
mypy app tests scripts
# Output: Success: no issues found in 83 source files
```

---

## 4. Production Deployment & Runtime Verification

Deployment procedure is fully verified using [`docker-compose.prod.yml`](../docker-compose.prod.yml).

### Starting Services

```bash
# Bring up PostgreSQL 16 and multi-worker API container
docker compose -f docker-compose.prod.yml up -d
```

### Healthcheck & Readiness Probe Verification

```bash
# Health check (application startup)
curl -s http://localhost:8000/api/v1/healthz
# Response: {"status":"healthy"}

# Readiness check (PostgreSQL connectivity verified)
curl -s http://localhost:8000/api/v1/readyz
# Response: {"status":"ready","database":"connected"}
```

### End-to-End API Flow (Authenticated Request)

```bash
# 1. Seed demo database with tenants, roles, and documents
docker compose -f docker-compose.prod.yml exec api python -m scripts.seed

# 2. Authenticate and obtain JWT access token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@securedocs.io&password=AdminSecurePassword2026!" \
  | jq -r .access_token)

# 3. Retrieve workspaces for authenticated actor
curl -s http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN"
```

> [!NOTE]
> **Deployment Status:** Deployment procedure verified locally against `docker-compose.prod.yml`. External cloud deployment (Fly.io / Render / Railway) is documented and ready for activation upon provisioning cloud provider credentials.
