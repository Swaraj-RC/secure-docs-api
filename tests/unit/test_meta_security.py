from fastapi.routing import APIRoute

from app.api.deps import bearer_scheme, get_current_user
from app.main import create_app

PUBLIC_ROUTES = {
    "/api/v1/healthz",
    "/api/v1/readyz",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
}

DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


def test_meta_assert_all_non_public_routes_require_authentication() -> None:
    app = create_app()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        path = route.path
        if path in PUBLIC_ROUTES or path in DOCS_PATHS:
            continue

        # Inspect all dependencies (both router-level and endpoint function parameters)
        flat_deps = [d.call for d in route.dependant.dependencies]
        nested_deps = []
        for d in route.dependant.dependencies:
            nested_deps.extend([sub.call for sub in d.dependencies])

        all_calls = set(flat_deps + nested_deps)

        has_auth_dep = get_current_user in all_calls or bearer_scheme in all_calls

        assert has_auth_dep, (
            f"SECURITY VIOLATION: Route '{path}' [{','.join(route.methods)}] "
            "is not in the public allowlist and has no authentication dependency attached!"
        )

