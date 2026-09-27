"""Install operation-level student record permissions for M28-1."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0043_m28_student_record_perms"
down_revision: str | None = "0042_m27_true_recurrence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("students.read", "Read minimized student records within authorized institution scope."),
    ("students.manage", "Create and update bounded student profile fields."),
    ("enrollments.manage", "Create and manage enrollment through its bounded domain commands."),
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, description in PERMISSIONS:
        existing = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (id, key, description) "
                    "VALUES (:id, :key, :description)"
                ),
                {"id": uuid4(), "key": key, "description": description},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE key IN "
            "('students.read', 'students.manage', 'enrollments.manage'))"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN "
            "('students.read', 'students.manage', 'enrollments.manage')"
        )
    )
