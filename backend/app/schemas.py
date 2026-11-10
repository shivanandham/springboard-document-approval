import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus, EventType


class AppError(Exception):
    def __init__(
        self, status: int, code: str, message: str, fields: dict[str, str] | None = None
    ) -> None:
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]


class UserRef(ORM):
    id: uuid.UUID
    full_name: str
    email: str


class FileOut(ORM):
    id: uuid.UUID
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class DocumentOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    status: DocumentStatus
    version: int
    submitter: UserRef
    decided_by: UserRef | None
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime
    updated_at: datetime
    file: FileOut | None


class EventOut(ORM):
    id: uuid.UUID
    event: EventType
    from_status: DocumentStatus | None
    to_status: DocumentStatus
    comment: str | None
    actor: UserRef
    created_at: datetime


class DocumentDetail(DocumentOut):
    events: list[EventOut]


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = None
    version: int = Field(ge=1)


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: dict[str, str] = {}


class ErrorOut(BaseModel):
    error: ErrorBody
