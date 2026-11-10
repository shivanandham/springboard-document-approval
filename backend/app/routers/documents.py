import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import StringConstraints

from app import services
from app.db import SessionDep
from app.models import DocumentStatus, User
from app.schemas import DecisionIn, DocumentDetail, DocumentOut, DocumentPage, ErrorOut
from app.security import require_permission
from app.storage import storage

router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
    responses={code: {"model": ErrorOut} for code in (400, 401, 403, 404)},
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None


@router.post(
    "",
    status_code=201,
    summary="Submit a document for review",
    responses={413: {"model": ErrorOut}, 415: {"model": ErrorOut}},
)
async def create_document(
    session: SessionDep,
    user: Annotated[User, require_permission("document:create")],
    title: Annotated[Title, Form()],
    file: Annotated[UploadFile, File(description="PDF, DOCX, PNG, JPG or TXT")],
    description: Annotated[Description, Form()] = None,
) -> DocumentOut:
    return await services.create_document(session, user, title, description, file)


@router.get("", summary="List documents (submitters see only their own)")
async def list_documents(
    session: SessionDep,
    user: Annotated[User, require_permission("document:read_own", "document:read_all")],
    status: DocumentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Literal["-created_at", "created_at"] = "-created_at",
) -> DocumentPage:
    items, total = await services.list_documents(session, user, status, limit, offset, sort)
    return DocumentPage(items=items, total=total)


@router.get("/{document_id}", summary="Get a document with its file metadata and event trail")
async def get_document(
    session: SessionDep,
    user: Annotated[User, require_permission("document:read_own", "document:read_all")],
    document_id: uuid.UUID,
) -> DocumentDetail:
    return await services.get_document(session, user, document_id, "document:read_all", events=True)


@router.get(
    "/{document_id}/file",
    summary="Download the document's file",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_file(
    session: SessionDep,
    user: Annotated[User, require_permission("file:download_own", "file:download_all")],
    document_id: uuid.UUID,
) -> StreamingResponse:
    doc = await services.get_document(session, user, document_id, "file:download_all")
    if doc.file is None:
        raise services.not_found("File")
    name = quote(doc.file.original_name)
    disposition = (
        f'attachment; filename="{name}"'
        if name == doc.file.original_name
        else f"attachment; filename*=UTF-8''{name}"
    )
    return StreamingResponse(
        storage.open(doc.file.storage_key),
        media_type=doc.file.content_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(doc.file.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{document_id}/decision",
    summary="Approve or reject a pending document",
    responses={409: {"model": ErrorOut}},
)
async def decide(
    session: SessionDep,
    user: Annotated[User, require_permission("document:review")],
    document_id: uuid.UUID,
    body: DecisionIn,
) -> DocumentOut:
    """Rejecting needs a comment. `version` must match the document's current version,
    otherwise the decision is refused with 409 so a stale screen can't overwrite a newer one."""
    return await services.decide(
        session, user, document_id, body.decision, body.comment, body.version
    )
