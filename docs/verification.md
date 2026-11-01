# Verification

## In CI (source of truth)
- Job `test-postgres` in `.github/workflows/ci.yml` runs the full suite against PostgreSQL 16 and asserts the migration cycle (upgrade head → downgrade base → upgrade head).
- See the GitHub Actions tab for the latest green run and coverage.

## Local production-compose check
Docker was unavailable in the build environment, so this was not executed here.
To verify locally:

    docker compose -f docker-compose.prod.yml up -d
    curl -fsS http://localhost:8000/healthz
    curl -fsS http://localhost:8000/readyz
    python scripts/seed.py
    # open http://localhost:8000/docs
