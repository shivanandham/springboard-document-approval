import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import PurePath
from typing import Literal

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Document,
    DocumentEvent,
    DocumentFile,
    DocumentStatus,
    EventType,
    Role,
    User,
    user_roles,
)
from app.schemas import AppError
from app.security import hash_password
from app.storage import CHUNK_SIZE, storage

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}


def not_found(what: str = "Document") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found")


async def create_document(
    session: AsyncSession, user: User, title: str, description: str | None, upload: UploadFile
) -> Document:
    """Stream the upload to a temp key, insert rows, commit, then move the file into place."""
    original_name = PurePath(upload.filename or "").name
    content_type = ALLOWED_TYPES.get(PurePath(original_name).suffix.lower())
    if content_type is None:
        raise AppError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "Allowed file types are PDF, DOCX, PNG, JPG and TXT",
            {"file": "Unsupported file type"},
        )

    limit = settings.max_upload_mb * 1024 * 1024
    digest, size = hashlib.sha256(), 0

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal size
        while chunk := await upload.read(CHUNK_SIZE):
            size += len(chunk)
            if size > limit:
                raise AppError(
                    413,
                    "FILE_TOO_LARGE",
                    f"Files can be at most {settings.max_upload_mb} MB",
                    {"file": "File too large"},
                )
            digest.update(chunk)
            yield chunk

    doc_id, file_id = uuid.uuid4(), uuid.uuid4()
    temp_key, final_key = f"tmp/{file_id}", f"documents/{doc_id}/{file_id}"
    try:
        await storage.save(temp_key, chunks())
        if size == 0:
            raise AppError(400, "VALIDATION_ERROR", "The file is empty", {"file": "File is empty"})
        session.add(
            Document(
                id=doc_id,
                submitter_id=user.id,
                title=title,
                description=description or None,
                files=[
                    DocumentFile(
                        id=file_id,
                        storage_key=final_key,
                        original_name=original_name[-255:],
                        content_type=content_type,
                        size_bytes=size,
                        sha256=digest.hexdigest(),
                    )
                ],
            )
        )
        session.add(
            DocumentEvent(
                document_id=doc_id,
                actor_id=user.id,
                event=EventType.submitted,
                to_status=DocumentStatus.pending,
            )
        )
        await session.commit()
    except BaseException:
        await storage.delete(temp_key)
        raise
    await storage.move(temp_key, final_key)
    return await _load(session, doc_id)


def _visible(user: User, all_permission: str):
    query = select(Document)
    if all_permission not in user.permissions:
        query = query.where(Document.submitter_id == user.id)
    return query


async def _load(session: AsyncSession, doc_id: uuid.UUID, query=None, events=False) -> Document:
    query = (query if query is not None else select(Document)).where(Document.id == doc_id)
    if events:
        query = query.options(selectinload(Document.events))
    doc = await session.scalar(query.execution_options(populate_existing=True))
    if doc is None:
        raise not_found()
    return doc


async def list_documents(
    session: AsyncSession,
    user: User,
    status: DocumentStatus | None,
    limit: int,
    offset: int,
    sort: Literal["created_at", "-created_at"],
) -> tuple[list[Document], int]:
    query = _visible(user, "document:read_all")
    if status:
        query = query.where(Document.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    order = Document.created_at.desc() if sort.startswith("-") else Document.created_at.asc()
    items = await session.scalars(query.order_by(order, Document.id).limit(limit).offset(offset))
    return list(items), total or 0


async def get_document(
    session: AsyncSession, user: User, doc_id: uuid.UUID, all_permission: str, events=False
) -> Document:
    """Fetch a document the user may see. Others' documents are 404 so existence doesn't leak."""
    return await _load(session, doc_id, _visible(user, all_permission), events)


async def reseed_users() -> None:
    """Idempotently restore the seed users, their roles and their passwords from env."""
    seeds = [
        ("sam.submitter@docflow.dev", "Sam Carter", "submitter", settings.seed_submitter_password),
        ("riya.reviewer@docflow.dev", "Riya Menon", "reviewer", settings.seed_reviewer_password),
    ]
    async with SessionLocal() as session:
        for email, full_name, role, password in seeds:
            values = {
                "full_name": full_name,
                "password_hash": hash_password(password),
                "is_active": True,
            }
            user_id = await session.scalar(
                insert(User)
                .values(email=email, **values)
                .on_conflict_do_update(
                    index_elements=[User.email], set_={**values, "updated_at": func.now()}
                )
                .returning(User.id)
            )
            role_id = select(Role.id).where(Role.name == role).scalar_subquery()
            await session.execute(
                insert(user_roles).values(user_id=user_id, role_id=role_id).on_conflict_do_nothing()
            )
        await session.commit()
