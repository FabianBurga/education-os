"""Add explicit operation permissions for academic structure."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0045_m28_academic_permissions"
down_revision: str | None = "0044_m28_enrollment_read"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for key, description in (
        ("academics.read", "Read academic structure within the authorized institution."),
        ("academics.manage", "Create and maintain academic structure within the authorized institution."),
        ("academics.assign", "Manage scoped teaching assignments and placement commands."),
    ):
        exists = bind.execute(sa.text("SELECT 1 FROM permissions WHERE key=:key"), {"key": key}).first()
        if exists is None:
            bind.execute(
                sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
                {"id": uuid4(), "key": key, "description": description},
            )


def downgrade() -> None:
    bind = op.get_bind()
    keys = ("academics.read", "academics.manage", "academics.assign")
    permission_ids = bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"),
        {"keys": list(keys)},
    ).scalars().all()
    for permission_id in permission_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:id"), {"id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"), {"keys": list(keys)})
