"""M8 Administrator Console security/catalog support.

Revision ID: 0010_m8
Revises: 0009_rc5
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0010_m8"
down_revision: str | None = "0009_rc5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

M8_PERMISSIONS = (
    ("admin.console.access", "Access the institution Administrator Console."),
    ("admin.institution.manage", "Manage current institution settings and campuses."),
    ("admin.people.manage", "Manage people, accounts and staff profiles."),
    ("admin.academic.manage", "Manage academic setup through the Administrator Console."),
    (
        "admin.enrollment.manage",
        "Manage enrollment and family setup through the Administrator Console.",
    ),
    ("admin.roles.manage", "Manage institution roles and permission assignments."),
)

ADMIN_ACTOR_SQL = """
EXISTS (
    SELECT 1
    FROM memberships actor_m
    JOIN membership_roles actor_mr ON actor_mr.membership_id = actor_m.id
    JOIN role_permissions actor_rp ON actor_rp.role_id = actor_mr.role_id
    JOIN permissions actor_p ON actor_p.id = actor_rp.permission_id
    WHERE actor_m.user_id =
          NULLIF(current_setting('app.user_id', true), '')::uuid
      AND actor_m.institution_id =
          NULLIF(current_setting('app.institution_id', true), '')::uuid
      AND actor_m.status = 'ACTIVE'
      AND actor_p.key = 'admin.console.access'
)
"""

TARGET_CURRENT_INSTITUTION_SQL = """
EXISTS (
    SELECT 1
    FROM memberships target_m
    WHERE target_m.user_id = user_accounts.id
      AND target_m.institution_id =
          NULLIF(current_setting('app.institution_id', true), '')::uuid
)
"""


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("GRANT INSERT, UPDATE ON TABLE user_accounts TO education_app")

    permission_ids: dict[str, object] = {}
    for key, description in M8_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is None:
            permission_id = uuid4()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO permissions (id, key, description)
                    VALUES (:id, :key, :description)
                    """
                ),
                {"id": permission_id, "key": key, "description": description},
            )
        permission_ids[key] = permission_id

    institution_ids = bind.execute(
        sa.text("SELECT id FROM institutions")
    ).scalars().all()

    for institution_id in institution_ids:
        role_id = bind.execute(
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
        if role_id is None:
            role_id = uuid4()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO roles (id, institution_id, key, name)
                    VALUES (
                        :id,
                        :institution_id,
                        'SYSTEM_ADMIN',
                        'Administrador del sistema'
                    )
                    """
                ),
                {"id": role_id, "institution_id": institution_id},
            )

        for permission_id in permission_ids.values():
            bind.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (:role_id, :permission_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"role_id": role_id, "permission_id": permission_id},
            )

    op.execute(
        f"""
        CREATE POLICY user_accounts_admin_select_policy
        ON user_accounts
        FOR SELECT
        TO education_app
        USING (
            ({ADMIN_ACTOR_SQL})
            AND ({TARGET_CURRENT_INSTITUTION_SQL})
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY user_accounts_admin_insert_policy
        ON user_accounts
        FOR INSERT
        TO education_app
        WITH CHECK ({ADMIN_ACTOR_SQL})
        """
    )
    op.execute(
        f"""
        CREATE POLICY user_accounts_admin_update_policy
        ON user_accounts
        FOR UPDATE
        TO education_app
        USING (
            ({ADMIN_ACTOR_SQL})
            AND ({TARGET_CURRENT_INSTITUTION_SQL})
        )
        WITH CHECK (
            ({ADMIN_ACTOR_SQL})
            AND ({TARGET_CURRENT_INSTITUTION_SQL})
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.execute(
        "DROP POLICY IF EXISTS user_accounts_admin_update_policy ON user_accounts"
    )
    op.execute(
        "DROP POLICY IF EXISTS user_accounts_admin_insert_policy ON user_accounts"
    )
    op.execute(
        "DROP POLICY IF EXISTS user_accounts_admin_select_policy ON user_accounts"
    )
    op.execute("REVOKE INSERT, UPDATE ON TABLE user_accounts FROM education_app")

    for key, _description in M8_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is not None:
            bind.execute(
                sa.text(
                    "DELETE FROM role_permissions WHERE permission_id = :permission_id"
                ),
                {"permission_id": permission_id},
            )

    bind.execute(
        sa.text(
            """
            DELETE FROM roles r
            WHERE r.key = 'SYSTEM_ADMIN'
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  WHERE mr.role_id = r.id
              )
            """
        )
    )

    for key, _description in M8_PERMISSIONS:
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
