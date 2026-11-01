import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.pagination import Page, PageParams
from app.db.models.user import User
from app.schemas.audit import AuditLogResponse
from app.services.audit_service import list_user_audit_logs, list_workspace_audit_logs

router = APIRouter(tags=["audit"])


@router.get("/workspaces/{ws_id}/audit-logs", response_model=Page[AuditLogResponse])
async def get_workspace_audit_logs(
    ws_id: uuid.UUID,
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    pagination: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[AuditLogResponse]:
    page = await list_workspace_audit_logs(
        db=db,
        workspace_id=ws_id,
        actor_id=current_user.id,
        pagination=pagination,
        filter_actor_id=actor_id,
        filter_action=action,
        filter_resource_type=resource_type,
        date_from=date_from,
        date_to=date_to,
    )
    items = [AuditLogResponse.model_validate(log) for log in page.items]
    return Page.create(items=items, total=page.total, params=pagination)


@router.get("/audit-logs/me", response_model=Page[AuditLogResponse])
async def get_my_audit_logs(
    action: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    pagination: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[AuditLogResponse]:
    page = await list_user_audit_logs(
        db=db,
        actor_id=current_user.id,
        pagination=pagination,
        filter_action=action,
        date_from=date_from,
        date_to=date_to,
    )
    items = [AuditLogResponse.model_validate(log) for log in page.items]
    return Page.create(items=items, total=page.total, params=pagination)
