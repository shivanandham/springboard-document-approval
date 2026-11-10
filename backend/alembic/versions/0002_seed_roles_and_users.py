"""seed roles, permissions and users

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

import uuid

import sqlalchemy as sa
from argon2 import PasswordHasher

from alembic import op
from app.config import settings

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLES = {
    "submitter": (
        "Submits documents and tracks their status",
        ["document:create", "document:read_own", "file:download_own"],
    ),
    "reviewer": (
        "Reviews and decides on submitted documents",
        ["document:read_all", "document:review", "file:download_all"],
    ),
}
PERMISSIONS = [code for _, codes in ROLES.values() for code in codes]
USERS = [
    ("sam.submitter@docflow.dev", "Sam Carter", "submitter", settings.seed_submitter_password),
    ("riya.reviewer@docflow.dev", "Riya Menon", "reviewer", settings.seed_reviewer_password),
]

roles = sa.table("roles", sa.column("id"), sa.column("name"), sa.column("description"))
permissions = sa.table("permissions", sa.column("id"), sa.column("code"))
role_permissions = sa.table("role_permissions", sa.column("role_id"), sa.column("permission_id"))
users = sa.table(
    "users", sa.column("id"), sa.column("email"), sa.column("full_name"), sa.column("password_hash")
)
user_roles = sa.table("user_roles", sa.column("user_id"), sa.column("role_id"))


def upgrade() -> None:
    role_ids = {name: uuid.uuid4() for name in ROLES}
    perm_ids = {code: uuid.uuid4() for code in PERMISSIONS}
    user_ids = {email: uuid.uuid4() for email, *_ in USERS}
    hasher = PasswordHasher()

    op.bulk_insert(
        roles,
        [{"id": role_ids[n], "name": n, "description": d} for n, (d, _) in ROLES.items()],
    )
    op.bulk_insert(permissions, [{"id": i, "code": c} for c, i in perm_ids.items()])
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[name], "permission_id": perm_ids[code]}
            for name, (_, codes) in ROLES.items()
            for code in codes
        ],
    )
    op.bulk_insert(
        users,
        [
            {"id": user_ids[e], "email": e, "full_name": n, "password_hash": hasher.hash(p)}
            for e, n, _, p in USERS
        ],
    )
    op.bulk_insert(
        user_roles,
        [{"user_id": user_ids[e], "role_id": role_ids[r]} for e, _, r, _ in USERS],
    )


def downgrade() -> None:
    op.execute(users.delete().where(users.c.email.in_([e for e, *_ in USERS])))
    op.execute(permissions.delete().where(permissions.c.code.in_(PERMISSIONS)))
    op.execute(roles.delete().where(roles.c.name.in_(list(ROLES))))
