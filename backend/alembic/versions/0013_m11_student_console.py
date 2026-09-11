"""M11 Student Console permission catalog and student notice RLS.

Revision ID: 0013_m11
Revises: 0012_m10
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0013_m11"
down_revision: str | None = "0012_m10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

M11_PERMISSIONS = (
    (
        "student.console.access",
        "Access the scoped Student Console.",
    ),
    (
        "student.profile.view",
        "View the signed student's own academic profile.",
    ),
    (
        "student.classes.view",
        "View the signed student's own classes.",
    ),
    (
        "student.schedule.view",
        "View the signed student's own schedule.",
    ),
    (
        "student.attendance.view",
        "View the signed student's own attendance.",
    ),
    (
        "student.grades.view",
        "View the signed student's own grades and pending assessments.",
    ),
    (
        "student.notices.view",
        "View published notices visible to the signed student.",
    ),
    (
        "student.progress.view",
        "View derived progress metrics for the signed student.",
    ),
)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"

TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

STAFF_CURRENT = f"""
EXISTS (
    SELECT 1
    FROM user_accounts ua
    JOIN staff_profiles sp ON sp.person_id = ua.person_id
    WHERE ua.id = {USER_CTX}
      AND sp.institution_id = {INST_CTX}
      AND sp.status = 'ACTIVE'
)
"""

OWN_STUDENT_NOTICE = f"""
status = 'PUBLISHED'
AND (
    student_profile_id IS NULL
    OR EXISTS (
        SELECT 1
        FROM user_accounts ua
        JOIN student_profiles sp
          ON sp.person_id = ua.person_id
         AND sp.institution_id = {INST_CTX}
         AND sp.status = 'ACTIVE'
        WHERE ua.id = {USER_CTX}
          AND sp.id = family_notices.student_profile_id
    )
)
"""

GUARDIAN_NOTICE_VISIBLE = f"""
status = 'PUBLISHED'
AND (
    student_profile_id IS NULL
    OR EXISTS (
        SELECT 1
        FROM guardian_student_portal_access pa
        JOIN user_accounts ua ON ua.id = {USER_CTX}
        JOIN guardian_profiles gp
          ON gp.person_id = ua.person_id
         AND gp.id = pa.guardian_profile_id
        WHERE pa.student_profile_id = family_notices.student_profile_id
          AND pa.status = 'ACTIVE'
          AND gp.institution_id = {INST_CTX}
          AND gp.status = 'ACTIVE'
    )
)
"""


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


def _ensure_role(bind, institution_id):
    role_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM roles
            WHERE institution_id = :institution_id
              AND key = 'STUDENT'
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
            VALUES (:id, :institution_id, 'STUDENT', 'Estudiante')
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


def _replace_family_notice_policy_with_student_access() -> None:
    op.execute("DROP POLICY IF EXISTS family_notices_select ON family_notices")
    op.execute(
        f"""
        CREATE POLICY family_notices_select
        ON family_notices
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND (
                ({STAFF_CURRENT})
                OR ({GUARDIAN_NOTICE_VISIBLE})
                OR ({OWN_STUDENT_NOTICE})
            )
        )
        """
    )


def _restore_m6_family_notice_policy() -> None:
    op.execute("DROP POLICY IF EXISTS family_notices_select ON family_notices")
    op.execute(
        f"""
        CREATE POLICY family_notices_select
        ON family_notices
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND (
                ({STAFF_CURRENT})
                OR ({GUARDIAN_NOTICE_VISIBLE})
            )
        )
        """
    )


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M11_PERMISSIONS
    }

    institution_ids = bind.execute(
        sa.text("SELECT id FROM institutions")
    ).scalars().all()

    for institution_id in institution_ids:
        student_role = _ensure_role(bind, institution_id)
        for permission_id in permission_ids.values():
            _grant(bind, student_role, permission_id)

    _replace_family_notice_policy_with_student_access()


def downgrade() -> None:
    bind = op.get_bind()

    _restore_m6_family_notice_policy()

    permission_ids = []
    for key, _description in M11_PERMISSIONS:
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
            WHERE r.key = 'STUDENT'
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  WHERE mr.role_id = r.id
              )
            """
        )
    )

    for key, _description in M11_PERMISSIONS:
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
