import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class DocumentStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class EventType(StrEnum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


status_enum = Enum(DocumentStatus, name="document_status")
event_enum = Enum(EventType, name="document_event_type")

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True, index=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str] = mapped_column(Text)

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), default=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")

    @property
    def permissions(self) -> set[str]:
        return {p.code for role in self.roles for p in role.permissions}


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title_length"),
        CheckConstraint(
            "(status = 'pending' AND decided_by_id IS NULL AND decided_at IS NULL)"
            " OR (status <> 'pending' AND decided_by_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="decision_consistency",
        ),
        CheckConstraint(
            "status <> 'rejected' OR decision_comment IS NOT NULL", name="rejected_has_comment"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("char_length(description) <= 5000", name="description_length"),
        CheckConstraint("char_length(decision_comment) <= 5000", name="decision_comment_length"),
        Index("ix_documents_status_created_at", "status", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    submitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DocumentStatus] = mapped_column(
        status_enum, server_default=DocumentStatus.pending.value, default=DocumentStatus.pending
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(server_default=text("1"), default=1)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    submitter: Mapped[User] = relationship(foreign_keys=[submitter_id], lazy="selectin")
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id], lazy="selectin")
    files: Mapped[list["DocumentFile"]] = relationship(
        lazy="selectin", order_by="DocumentFile.created_at", passive_deletes=True
    )
    events: Mapped[list["DocumentEvent"]] = relationship(
        lazy="raise", order_by="DocumentEvent.created_at", passive_deletes=True
    )

    @property
    def file(self) -> "DocumentFile | None":
        return self.files[0] if self.files else None


class DocumentFile(Base):
    __tablename__ = "document_files"
    __table_args__ = (CheckConstraint("size_bytes > 0", name="size_positive"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at()


class DocumentEvent(Base):
    __tablename__ = "document_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    event: Mapped[EventType] = mapped_column(event_enum)
    from_status: Mapped[DocumentStatus | None] = mapped_column(status_enum)
    to_status: Mapped[DocumentStatus] = mapped_column(status_enum)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

    actor: Mapped[User] = relationship(lazy="selectin")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = created_at()
