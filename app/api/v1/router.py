from fastapi import APIRouter

from app.api.v1.endpoints import audit, auth, documents, health, workspaces

api_v1_router = APIRouter()

api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(auth.router)
api_v1_router.include_router(workspaces.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(audit.router)
