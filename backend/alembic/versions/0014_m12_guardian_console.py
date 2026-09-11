"""M12 Family / Guardian Console permission catalog.

Revision ID: 0014_m12
Revises: 0013_m11
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0014_m12"
down_revision: str | None = "0013_m11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

M12_PERMISSIONS = (
    (
        "guardian.console.access",
        "Access the scoped Guardian Console.",
    ),
    (
        "guardian.students.view",
        "View students explicitly linked to the signed guardian.",
    ),
    (
        "guardian.schedule.view",
        "View schedules for explicitly linked students.",
    ),
    (
        "guardian.attendance.view",
        "View attendance for explicitly linked students.",
    ),
    (
        "guardian.grades.view",
        "View grades and pending assessments for explicitly linked students.",
    ),
    (
        "guardian.notices.view",
        "View published notices visible to the signed guardian.",
    ),
    (
        "guardian.notices.acknowledge",
        "Acknowledge published notices visible to the signed guardian.",
    ),
    (
        "guardian.progress.view",
        "View derived academic progress for explicitly linked students.",
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


def _ensure_guardian_role(bind, institution_id):
    role_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM roles
            WHERE institution_id = :institution_id
              AND key = 'GUARDIAN'
            """
        ),
        {"institution_id": institution_id},
    ).scalar_one_or_none()
    if role_id is not None:
        return role_id

    role_id = uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO roles (id, institution_id, key, name)
            VALUES (:id, :institution_id, 'GUARDIAN', 'Representante familiar')
            """
        ),
        {
            "id": role_id,
            "institution_id": institution_id,
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
        for key, description in M12_PERMISSIONS
    }

    institution_ids = bind.execute(
        sa.text("SELECT id FROM institutions")
    ).scalars().all()

    for institution_id in institution_ids:
        guardian_role = _ensure_guardian_role(bind, institution_id)
        for permission_id in permission_ids.values():
            _grant(bind, guardian_role, permission_id)


def downgrade() -> None:
    bind = op.get_bind()

    permission_ids = []
    for key, _description in M12_PERMISSIONS:
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
            WHERE r.key = 'GUARDIAN'
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  WHERE mr.role_id = r.id
              )
            """
        )
    )

    for key, _description in M12_PERMISSIONS:
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
