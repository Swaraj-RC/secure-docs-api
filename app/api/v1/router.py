from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, workspaces

api_v1_router = APIRouter()

api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(auth.router)
api_v1_router.include_router(workspaces.router)
