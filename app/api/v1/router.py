"""API v1 router — mounts all endpoint groups."""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_v1_router = APIRouter()

# Health checks (no auth required)
api_v1_router.include_router(health.router, tags=["health"])

# Additional endpoint routers will be added as they are built:
# Day 3: auth
# Day 4: workspaces, members
# Day 6: documents
# Day 7: versions
# Day 9: shares
# Day 10: audit
