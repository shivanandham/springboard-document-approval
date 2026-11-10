"""cap description and decision comment at 5000 characters

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

LIMITS = {
    "ck_documents_description_length": "char_length(description) <= 5000",
    "ck_documents_decision_comment_length": "char_length(decision_comment) <= 5000",
}


def upgrade() -> None:
    for name, condition in LIMITS.items():
        op.create_check_constraint(op.f(name), "documents", condition)


def downgrade() -> None:
    for name in LIMITS:
        op.drop_constraint(op.f(name), "documents", type_="check")
