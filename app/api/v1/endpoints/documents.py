import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.pagination import Page, PageParams
from app.db.models.document import DocClassification, DocStatus
from app.db.models.user import User
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentUpdate
from app.services.document_service import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    restore_document,
    update_document,
)

router = APIRouter(tags=["documents"])


@router.post(
    "/workspaces/{ws_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new document in a workspace",
)
async def create_document_endpoint(
    ws_id: uuid.UUID,
    payload: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    doc = await create_document(db=db, actor=current_user, ws_id=ws_id, payload=payload)
    return DocumentResponse.model_validate(doc)


@router.get(
    "/workspaces/{ws_id}/documents",
    response_model=Page[DocumentResponse],
    summary="List and filter documents in a workspace",
)
async def list_documents_endpoint(
    ws_id: uuid.UUID,
    q: str | None = Query(default=None, description="Search term"),
    status: DocStatus | None = Query(default=None, description="Status"),
    classification: DocClassification | None = Query(default=None, description="Classification"),
    owner_id: uuid.UUID | None = Query(default=None, description="Owner ID"),
    created_after: datetime | None = Query(default=None, description="Start date"),
    created_before: datetime | None = Query(default=None, description="End date"),
    sort: str = Query(default="-created_at", description="Sort expression: [+/-]col"),
    pagination: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Page[DocumentResponse]:
    page = await list_documents(
        db=db,
        actor=current_user,
        ws_id=ws_id,
        pagination=pagination,
        q=q,
        status=status,
        classification=classification,
        owner_id=owner_id,
        created_after=created_after,
        created_before=created_before,
        sort=sort,
    )
    items = [DocumentResponse.model_validate(item) for item in page.items]
    return Page(
        items=items,
        page=page.page,
        size=page.size,
        total=page.total,
        pages=page.pages,
    )


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
async def get_document_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    doc = await get_document(db=db, actor=current_user, doc_id=doc_id)
    return DocumentResponse.model_validate(doc)


@router.patch(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    summary="Update document metadata",
)
async def update_document_endpoint(
    doc_id: uuid.UUID,
    payload: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    doc = await update_document(db=db, actor=current_user, doc_id=doc_id, payload=payload)
    return DocumentResponse.model_validate(doc)


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a document",
)
async def delete_document_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_document(db=db, actor=current_user, doc_id=doc_id)


@router.post(
    "/documents/{doc_id}/restore",
    response_model=DocumentResponse,
    summary="Restore a soft-deleted document",
)
async def restore_document_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    doc = await restore_document(db=db, actor=current_user, doc_id=doc_id)
    return DocumentResponse.model_validate(doc)
