import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.pagination import Page, PageParams
from app.db.models.document import DocClassification, DocStatus
from app.db.models.user import User
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentUpdate
from app.schemas.share import ShareCreate, ShareResponse
from app.schemas.version import VersionResponse
from app.services.document_service import (
    create_document,
    delete_document,
    get_document,
    get_document_version_for_download,
    list_document_versions,
    list_documents,
    restore_document,
    update_document,
    upload_document_version,
)
from app.services.download_service import format_content_disposition, parse_range_header
from app.services.share_service import grant_share, list_shares, revoke_share
from app.storage import get_storage
from app.storage.base import StorageBackend

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


@router.post(
    "/documents/{doc_id}/versions",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new immutable file version",
)
async def upload_version_endpoint(
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> VersionResponse:
    version = await upload_document_version(
        db=db,
        storage=storage,
        actor=current_user,
        doc_id=doc_id,
        file=file,
    )
    return VersionResponse.model_validate(version)


@router.get(
    "/documents/{doc_id}/versions",
    response_model=list[VersionResponse],
    summary="List all immutable file versions for a document",
)
async def list_versions_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[VersionResponse]:
    versions = await list_document_versions(db=db, actor=current_user, doc_id=doc_id)
    return [VersionResponse.model_validate(v) for v in versions]


@router.get(
    "/documents/{doc_id}/versions/{vid}/download",
    summary="Download file version with range request support and security headers",
)
async def download_version_endpoint(
    doc_id: uuid.UUID,
    vid: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    _doc, version = await get_document_version_for_download(
        db=db,
        actor=current_user,
        doc_id=doc_id,
        version_id=vid,
    )

    disposition = format_content_disposition(version.original_filename)
    range_header = request.headers.get("Range")

    base_headers = {
        "Content-Disposition": disposition,
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "ETag": f'"{version.checksum_sha256}"',
    }

    if range_header:
        byte_range = parse_range_header(range_header, version.size_bytes)
        if byte_range:
            start, end = byte_range
            length = end - start + 1
            stream = await storage.get(version.storage_key, offset=start, length=length)
            headers = {
                **base_headers,
                "Content-Range": f"bytes {start}-{end}/{version.size_bytes}",
                "Content-Length": str(length),
            }
            return StreamingResponse(
                stream,
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=version.mime_type,
                headers=headers,
            )

    stream = await storage.get(version.storage_key)
    headers = {
        **base_headers,
        "Content-Length": str(version.size_bytes),
    }
    return StreamingResponse(
        stream,
        status_code=status.HTTP_200_OK,
        media_type=version.mime_type,
        headers=headers,
    )


@router.post(
    "/documents/{doc_id}/shares",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant or update document access share",
)
async def grant_share_endpoint(
    doc_id: uuid.UUID,
    payload: ShareCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareResponse:
    share = await grant_share(db=db, actor=current_user, doc_id=doc_id, payload=payload)
    return ShareResponse.model_validate(share)


@router.get(
    "/documents/{doc_id}/shares",
    response_model=list[ShareResponse],
    summary="List active document shares",
)
async def list_shares_endpoint(
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ShareResponse]:
    shares = await list_shares(db=db, actor=current_user, doc_id=doc_id)
    return [ShareResponse.model_validate(s) for s in shares]


@router.delete(
    "/documents/{doc_id}/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a document share",
)
async def revoke_share_endpoint(
    doc_id: uuid.UUID,
    share_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await revoke_share(db=db, actor=current_user, doc_id=doc_id, share_id=share_id)
