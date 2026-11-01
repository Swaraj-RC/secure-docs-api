import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.pagination import Page, PageParams
from app.db.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.workspace import (
    MemberAdd,
    MemberResponse,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.workspace_service import (
    add_member,
    create_workspace,
    delete_workspace,
    get_workspace_and_member,
    list_members,
    list_user_workspaces,
    remove_member,
    update_member_role,
    update_workspace,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
)
async def create_workspace_endpoint(
    payload: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    ws = await create_workspace(db=db, actor=current_user, payload=payload)
    return WorkspaceResponse.model_validate(ws)


@router.get(
    "",
    response_model=Page[WorkspaceResponse],
    summary="List workspaces where the caller is a member",
)
async def list_workspaces_endpoint(
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[WorkspaceResponse]:
    return await list_user_workspaces(db=db, actor=current_user, params=params)


@router.get(
    "/{ws_id}",
    response_model=WorkspaceResponse,
    summary="Get workspace details by ID",
)
async def get_workspace_endpoint(
    ws_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    ws, _ = await get_workspace_and_member(db=db, actor=current_user, ws_id=ws_id)
    return WorkspaceResponse.model_validate(ws)


@router.patch(
    "/{ws_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace details (owner/admin only)",
)
async def update_workspace_endpoint(
    ws_id: uuid.UUID,
    payload: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    ws = await update_workspace(db=db, actor=current_user, ws_id=ws_id, payload=payload)
    return WorkspaceResponse.model_validate(ws)


@router.delete(
    "/{ws_id}",
    response_model=MessageResponse,
    summary="Delete workspace (owner only)",
)
async def delete_workspace_endpoint(
    ws_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await delete_workspace(db=db, actor=current_user, ws_id=ws_id)
    return MessageResponse(message="Workspace successfully deleted")


# --- Workspace Members ---


@router.get(
    "/{ws_id}/members",
    response_model=Page[MemberResponse],
    summary="List workspace members",
)
async def list_members_endpoint(
    ws_id: uuid.UUID,
    params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[MemberResponse]:
    return await list_members(db=db, actor=current_user, ws_id=ws_id, params=params)


@router.post(
    "/{ws_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to the workspace",
)
async def add_member_endpoint(
    ws_id: uuid.UUID,
    payload: MemberAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    return await add_member(db=db, actor=current_user, ws_id=ws_id, payload=payload)


@router.patch(
    "/{ws_id}/members/{user_id}",
    response_model=MemberResponse,
    summary="Change a workspace member's role",
)
async def update_member_role_endpoint(
    ws_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberResponse:
    return await update_member_role(
        db=db,
        actor=current_user,
        ws_id=ws_id,
        target_user_id=user_id,
        payload=payload,
    )


@router.delete(
    "/{ws_id}/members/{user_id}",
    response_model=MessageResponse,
    summary="Remove a member from the workspace or leave",
)
async def remove_member_endpoint(
    ws_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await remove_member(db=db, actor=current_user, ws_id=ws_id, target_user_id=user_id)
    return MessageResponse(message="Member successfully removed from workspace")

