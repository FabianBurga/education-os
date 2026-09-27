"""Add explicit institutional attendance permissions for M28-5."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0046_m28_attendance_perms"
down_revision: str | None = "0045_m28_academic_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    ("attendance.read", "Read attendance records within authorized institution scope."),
    ("attendance.manage", "Manage attendance codes, sessions, and new attendance facts."),
    ("attendance.correct", "Correct existing attendance facts with evidence and current state."),
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, description in PERMISSIONS:
        if bind.execute(
            sa.text("SELECT 1 FROM permissions WHERE key=:key"), {"key": key}
        ).first() is None:
            bind.execute(
                sa.text(
                    "INSERT INTO permissions (id, key, description) "
                    "VALUES (:id, :key, :description)"
                ),
                {"id": uuid4(), "key": key, "description": description},
            )


def downgrade() -> None:
    raise NotImplementedError("M28-5 attendance permission migration is forward-only")
