"""init

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

document_status = postgresql.ENUM(
    "pending", "approved", "rejected", name="document_status", create_type=False
)
document_event_type = postgresql.ENUM(
    "submitted", "approved", "rejected", name="document_event_type", create_type=False
)


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    document_status.create(bind)
    document_event_type.create(bind)

    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "roles",
        _id(),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    op.create_table(
        "permissions",
        _id(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "permission_id",
            sa.Uuid(),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        op.f("ix_role_permissions_permission_id"), "role_permissions", ["permission_id"]
    )
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"])

    op.create_table(
        "documents",
        _id(),
        sa.Column("submitter_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", document_status, server_default="pending", nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_comment", sa.Text()),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 200", name=op.f("ck_documents_title_length")
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND decided_by_id IS NULL AND decided_at IS NULL)"
            " OR (status <> 'pending' AND decided_by_id IS NOT NULL AND decided_at IS NOT NULL)",
            name=op.f("ck_documents_decision_consistency"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR decision_comment IS NOT NULL",
            name=op.f("ck_documents_rejected_has_comment"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_documents_version_positive")),
    )
    op.create_index(op.f("ix_documents_submitter_id"), "documents", ["submitter_id"])
    op.create_index(op.f("ix_documents_decided_by_id"), "documents", ["decided_by_id"])
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", sa.literal_column("created_at DESC")],
    )

    op.create_table(
        "document_files",
        _id(),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_document_files_size_positive")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_document_files_storage_key")),
    )
    op.create_index(op.f("ix_document_files_document_id"), "document_files", ["document_id"])

    op.create_table(
        "document_events",
        _id(),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event", document_event_type, nullable=False),
        sa.Column("from_status", document_status),
        sa.Column("to_status", document_status, nullable=False),
        sa.Column("comment", sa.Text()),
        _timestamp("created_at"),
    )
    op.create_index(op.f("ix_document_events_document_id"), "document_events", ["document_id"])
    op.create_index(op.f("ix_document_events_actor_id"), "document_events", ["actor_id"])

    op.create_table(
        "refresh_tokens",
        _id(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "replaced_by_id", sa.Uuid(), sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")
        ),
        _timestamp("created_at"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"])
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"])
    op.create_index(op.f("ix_refresh_tokens_replaced_by_id"), "refresh_tokens", ["replaced_by_id"])


def downgrade() -> None:
    for table in (
        "refresh_tokens",
        "document_events",
        "document_files",
        "documents",
        "user_roles",
        "role_permissions",
        "permissions",
        "roles",
        "users",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    document_event_type.drop(bind)
    document_status.drop(bind)
