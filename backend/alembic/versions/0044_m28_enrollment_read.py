"""Add the bounded M28 enrollment read permission."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0044_m28_enrollment_read"
down_revision: str | None = "0043_m28_student_record_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM permissions WHERE key='enrollments.read'")
    ).first()
    if exists is None:
        bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
            {
                "id": uuid4(),
                "key": "enrollments.read",
                "description": "Read enrollment records and history within authorized institution scope.",
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE key='enrollments.read')"
        )
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE key='enrollments.read'"))
