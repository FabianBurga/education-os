"""M10 Teacher Console permission catalog.

Revision ID: 0012_m10
Revises: 0011_m9
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0012_m10"
down_revision: str | None = "0011_m9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

M10_PERMISSIONS = (
    (
        "teacher.console.access",
        "Access the scoped Teacher Console.",
    ),
    (
        "teacher.classes.view",
        "View classes and rosters assigned to the current teacher.",
    ),
    (
        "teacher.attendance.manage",
        "Create class sessions and mark attendance for assigned classes.",
    ),
    (
        "teacher.grades.manage",
        "Create assessments and record grades for assigned classes.",
    ),
    (
        "teacher.tasks.manage",
        "Review and complete TEACHER workflow tasks for assigned sections.",
    ),
)


def _permission_id(bind, key: str, description: str):
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"),
        {"key": key},
    ).scalar_one_or_none()
    if permission_id is not None:
        return permission_id

    permission_id = uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO permissions (id, key, description)
            VALUES (:id, :key, :description)
            """
        ),
        {
            "id": permission_id,
            "key": key,
            "description": description,
        },
    )
    return permission_id


def _ensure_role(bind, institution_id, key: str, name: str):
    role_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM roles
            WHERE institution_id = :institution_id
              AND key = :key
            """
        ),
        {
            "institution_id": institution_id,
            "key": key,
        },
    ).scalar_one_or_none()
    if role_id is not None:
        return role_id

    role_id = uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO roles (id, institution_id, key, name)
            VALUES (:id, :institution_id, :key, :name)
            """
        ),
        {
            "id": role_id,
            "institution_id": institution_id,
            "key": key,
            "name": name,
        },
    )
    return role_id


def _grant(bind, role_id, permission_id) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (:role_id, :permission_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "role_id": role_id,
            "permission_id": permission_id,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M10_PERMISSIONS
    }

    institution_ids = bind.execute(
        sa.text("SELECT id FROM institutions")
    ).scalars().all()

    for institution_id in institution_ids:
        teacher_role = _ensure_role(
            bind,
            institution_id,
            "TEACHER",
            "Docente",
        )
        role_ids = [teacher_role]

        system_admin = bind.execute(
            sa.text(
                """
                SELECT id
                FROM roles
                WHERE institution_id = :institution_id
                  AND key = 'SYSTEM_ADMIN'
                """
            ),
            {"institution_id": institution_id},
        ).scalar_one_or_none()
        if system_admin is not None:
            role_ids.append(system_admin)

        for role_id in role_ids:
            for permission_id in permission_ids.values():
                _grant(bind, role_id, permission_id)


def downgrade() -> None:
    bind = op.get_bind()

    permission_ids = []
    for key, _description in M10_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is not None:
            permission_ids.append(permission_id)

    for permission_id in permission_ids:
        bind.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE permission_id = :permission_id
                """
            ),
            {"permission_id": permission_id},
        )

    bind.execute(
        sa.text(
            """
            DELETE FROM roles r
            WHERE r.key = 'TEACHER'
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  WHERE mr.role_id = r.id
              )
            """
        )
    )

    for key, _description in M10_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                DELETE FROM permissions p
                WHERE p.key = :key
                  AND NOT EXISTS (
                      SELECT 1
                      FROM role_permissions rp
                      WHERE rp.permission_id = p.id
                  )
                """
            ),
            {"key": key},
        )
