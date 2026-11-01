import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.pagination import Page, PageParams
from app.db.models.user import User
from app.db.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.schemas.workspace import (
    MemberAdd,
    MemberResponse,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)


async def create_workspace(
    db: AsyncSession,
    actor: User,
    payload: WorkspaceCreate,
) -> Workspace:
    slug_check = select(Workspace).where(Workspace.slug == payload.slug)
    if await db.scalar(slug_check):
        raise ConflictError(f"Workspace slug '{payload.slug}' is already taken", code="CONFLICT")

    ws = Workspace(
        name=payload.name,
        slug=payload.slug,
        owner_id=actor.id,
        is_active=True,
    )
    db.add(ws)
    await db.flush()

    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=actor.id,
        role=WorkspaceRole.OWNER,
    )
    db.add(member)
    await db.commit()
    await db.refresh(ws)
    return ws


async def get_workspace_and_member(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
) -> tuple[Workspace, WorkspaceMember]:
    # Leakage prevention: check workspace and membership together
    stmt = (
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(Workspace.id == ws_id)
        .where(WorkspaceMember.user_id == actor.id)
        .where(Workspace.is_active.is_(True))
    )
    result = (await db.execute(stmt)).first()
    if not result:
        raise NotFoundError("Workspace not found", code="NOT_FOUND")

    ws, member = result
    return ws, member


async def list_user_workspaces(
    db: AsyncSession,
    actor: User,
    params: PageParams,
) -> Page[WorkspaceResponse]:
    base_query = (
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == actor.id)
        .where(Workspace.is_active.is_(True))
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.scalar(count_query)) or 0

    items_query = (
        base_query.order_by(Workspace.created_at.desc()).offset(params.offset).limit(params.size)
    )
    workspaces = (await db.scalars(items_query)).all()

    items = [WorkspaceResponse.model_validate(w) for w in workspaces]
    return Page.create(items=items, total=total, params=params)


async def update_workspace(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    payload: WorkspaceUpdate,
) -> Workspace:
    ws, member = await get_workspace_and_member(db, actor, ws_id)
    if member.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        raise ForbiddenError("Admin or Owner role required to update workspace", code="FORBIDDEN")

    if payload.name is not None:
        ws.name = payload.name

    await db.commit()
    await db.refresh(ws)
    return ws


async def delete_workspace(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
) -> None:
    ws, member = await get_workspace_and_member(db, actor, ws_id)
    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenError("Only workspace owner can delete workspace", code="FORBIDDEN")

    await db.delete(ws)
    await db.commit()


async def list_members(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    params: PageParams,
) -> Page[MemberResponse]:
    await get_workspace_and_member(db, actor, ws_id)

    base_query = (
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == ws_id)
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.scalar(count_query)) or 0

    items_query = (
        base_query.order_by(WorkspaceMember.created_at.asc())
        .offset(params.offset)
        .limit(params.size)
    )
    rows = (await db.execute(items_query)).all()

    items = [
        MemberResponse(
            id=mem.id,
            workspace_id=mem.workspace_id,
            user_id=mem.user_id,
            role=mem.role,
            email=usr.email,
            full_name=usr.full_name,
            created_at=mem.created_at,
        )
        for mem, usr in rows
    ]
    return Page.create(items=items, total=total, params=params)


async def add_member(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    payload: MemberAdd,
) -> MemberResponse:
    _, actor_member = await get_workspace_and_member(db, actor, ws_id)
    if actor_member.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        raise ForbiddenError("Admin or Owner role required to invite members", code="FORBIDDEN")

    if payload.role == WorkspaceRole.OWNER:
        raise ValidationError("Cannot assign owner role directly", code="VALIDATION_ERROR")

    target_user = await db.scalar(select(User).where(User.email == payload.email))
    if not target_user:
        raise NotFoundError("User with specified email not found", code="NOT_FOUND")

    existing_mem = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == ws_id)
        .where(WorkspaceMember.user_id == target_user.id)
    )
    if existing_mem:
        raise ConflictError("User is already a member of this workspace", code="CONFLICT")

    new_member = WorkspaceMember(
        workspace_id=ws_id,
        user_id=target_user.id,
        role=payload.role,
        invited_by=actor.id,
    )
    db.add(new_member)
    await db.commit()
    await db.refresh(new_member)

    return MemberResponse(
        id=new_member.id,
        workspace_id=new_member.workspace_id,
        user_id=new_member.user_id,
        role=new_member.role,
        email=target_user.email,
        full_name=target_user.full_name,
        created_at=new_member.created_at,
    )


async def update_member_role(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberUpdate,
) -> MemberResponse:
    _, actor_member = await get_workspace_and_member(db, actor, ws_id)
    if actor_member.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        raise ForbiddenError("Admin or Owner role required to change roles", code="FORBIDDEN")

    target_mem = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == ws_id)
        .where(WorkspaceMember.user_id == target_user_id)
    )
    if not target_mem:
        raise NotFoundError("Member not found in workspace", code="NOT_FOUND")

    if target_mem.role == WorkspaceRole.OWNER and actor_member.role != WorkspaceRole.OWNER:
        raise ForbiddenError("Only the workspace owner can modify the owner", code="FORBIDDEN")

    if payload.role == WorkspaceRole.OWNER:
        raise ValidationError("Cannot transfer ownership via role change", code="VALIDATION_ERROR")

    target_mem.role = payload.role
    await db.commit()
    await db.refresh(target_mem)

    target_user = await db.get(User, target_user_id)
    assert target_user is not None

    return MemberResponse(
        id=target_mem.id,
        workspace_id=target_mem.workspace_id,
        user_id=target_mem.user_id,
        role=target_mem.role,
        email=target_user.email,
        full_name=target_user.full_name,
        created_at=target_mem.created_at,
    )


async def remove_member(
    db: AsyncSession,
    actor: User,
    ws_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> None:
    _, actor_member = await get_workspace_and_member(db, actor, ws_id)

    is_self_removal = actor.id == target_user_id
    if not is_self_removal and actor_member.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        raise ForbiddenError("Insufficient permissions to remove member", code="FORBIDDEN")

    target_mem = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == ws_id)
        .where(WorkspaceMember.user_id == target_user_id)
    )
    if not target_mem:
        raise NotFoundError("Member not found in workspace", code="NOT_FOUND")

    if target_mem.role == WorkspaceRole.OWNER:
        raise ForbiddenError("Workspace owner cannot leave or be removed", code="FORBIDDEN")

    if (
        actor_member.role == WorkspaceRole.ADMIN
        and target_mem.role == WorkspaceRole.ADMIN
        and not is_self_removal
    ):
        raise ForbiddenError("Admins cannot remove other admins", code="FORBIDDEN")

    await db.delete(target_mem)
    await db.commit()
