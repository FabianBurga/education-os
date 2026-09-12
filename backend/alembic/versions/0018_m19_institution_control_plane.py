"""M19 Institution Control Plane.

Revision ID: 0018_m19
Revises: 0017_m18
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_m19"
down_revision: str | None = "0017_m18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"

TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

CAN_VIEW = "education_os_control_plane_has_permission('control_plane.view')"
CAN_MANAGE = "education_os_control_plane_has_permission('control_plane.manage')"

M19_PERMISSIONS = (
    (
        "control_plane.view",
        "View the Institution Control Plane, capability state, policy state, "
        "change history, and operational health.",
    ),
    (
        "control_plane.manage",
        "Manage institution capabilities and control-plane policy state.",
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


def _tenant_indexes(table: str) -> None:
    op.create_index(
        f"ix_{table}_organization",
        table,
        ["organization_id"],
    )
    op.create_index(
        f"ix_{table}_institution",
        table,
        ["institution_id"],
    )


def _enable_control_rls(
    table: str,
    *,
    insert_allowed: bool,
    update_allowed: bool,
) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    privileges = ["SELECT"]
    if insert_allowed:
        privileges.append("INSERT")
    if update_allowed:
        privileges.append("UPDATE")

    op.execute(
        f'GRANT {", ".join(privileges)} ON "{table}" TO education_app'
    )

    op.execute(
        f"""
        CREATE POLICY {table}_select
        ON "{table}"
        FOR SELECT TO education_app
        USING ({TENANT} AND ({CAN_VIEW}))
        """
    )

    if insert_allowed:
        op.execute(
            f"""
            CREATE POLICY {table}_insert
            ON "{table}"
            FOR INSERT TO education_app
            WITH CHECK ({TENANT} AND ({CAN_MANAGE}))
            """
        )

    if update_allowed:
        op.execute(
            f"""
            CREATE POLICY {table}_update
            ON "{table}"
            FOR UPDATE TO education_app
            USING ({TENANT} AND ({CAN_MANAGE}))
            WITH CHECK ({TENANT} AND ({CAN_MANAGE}))
            """
        )


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M19_PERMISSIONS
    }

    role_rows = bind.execute(
        sa.text(
            """
            SELECT id, key
            FROM roles
            WHERE key IN ('SYSTEM_ADMIN', 'RECTOR')
            """
        )
    ).all()
    for role_id, role_key in role_rows:
        _grant(bind, role_id, permission_ids["control_plane.view"])
        if role_key == "SYSTEM_ADMIN":
            _grant(bind, role_id, permission_ids["control_plane.manage"])

    op.execute(
        """
        CREATE FUNCTION education_os_control_plane_has_permission(
            required_permission text
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                JOIN membership_roles mr
                  ON mr.membership_id = m.id
                JOIN role_permissions rp
                  ON rp.role_id = mr.role_id
                JOIN permissions p
                  ON p.id = rp.permission_id
                WHERE m.user_id = NULLIF(
                        current_setting('app.user_id', true),
                        ''
                    )::uuid
                  AND m.institution_id = NULLIF(
                        current_setting('app.institution_id', true),
                        ''
                    )::uuid
                  AND m.status = 'ACTIVE'
                  AND p.key = required_permission
            )
        $$
        """
    )
    op.execute(
        """
        REVOKE ALL
        ON FUNCTION education_os_control_plane_has_permission(text)
        FROM PUBLIC
        """
    )
    op.execute(
        """
        GRANT EXECUTE
        ON FUNCTION education_os_control_plane_has_permission(text)
        TO education_app
        """
    )

    op.create_table(
        "institution_control_state",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column(
            "revision",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("updated_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_institution_control_state_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user_accounts.id"],
            name="fk_institution_control_state_user",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "revision >= 0",
            name="ck_institution_control_state_revision",
        ),
        sa.UniqueConstraint(
            "institution_id",
            name="uq_institution_control_state_institution",
        ),
    )
    _tenant_indexes("institution_control_state")

    op.create_table(
        "institution_policy_controls",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "policy_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("updated_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_institution_policy_controls_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user_accounts.id"],
            name="fk_institution_policy_controls_user",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "policy_key ~ '^[a-z][a-z0-9_.-]{2,119}$'",
            name="ck_institution_policy_controls_key",
        ),
        sa.CheckConstraint(
            "policy_version >= 1",
            name="ck_institution_policy_controls_version",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "policy_key",
            name="uq_institution_policy_controls_inst_key",
        ),
    )
    _tenant_indexes("institution_policy_controls")
    op.create_index(
        "ix_institution_policy_controls_key",
        "institution_policy_controls",
        ["policy_key"],
    )
    op.create_index(
        "ix_institution_policy_controls_enabled",
        "institution_policy_controls",
        ["enabled"],
    )

    op.create_table(
        "institution_control_changes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("subject_key", sa.String(120), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "before_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "after_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_institution_control_changes_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_accounts.id"],
            name="fk_institution_control_changes_actor",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "revision > 0",
            name="ck_institution_control_changes_revision",
        ),
        sa.CheckConstraint(
            "change_type IN ('CAPABILITY', 'POLICY')",
            name="ck_institution_control_changes_type",
        ),
        sa.CheckConstraint(
            "length(trim(reason)) >= 3",
            name="ck_institution_control_changes_reason",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "revision",
            name="uq_institution_control_changes_inst_revision",
        ),
    )
    _tenant_indexes("institution_control_changes")
    op.create_index(
        "ix_institution_control_changes_subject",
        "institution_control_changes",
        ["change_type", "subject_key", "revision"],
    )
    op.create_index(
        "ix_institution_control_changes_lookup",
        "institution_control_changes",
        ["institution_id", "change_type", "subject_key", "revision"],
    )
    op.create_index(
        "ix_m19_event_ledger_institution_position",
        "event_ledger",
        ["institution_id", "position"],
    )
    op.create_index(
        "ix_m19_outbox_institution_created_id",
        "outbox_events",
        ["institution_id", "created_at", "id"],
    )
    op.create_index(
        "ix_institution_control_changes_created",
        "institution_control_changes",
        ["created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION education_os_reject_control_change_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'institution_control_changes is append-only; '
                'UPDATE, DELETE and TRUNCATE are forbidden';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_control_changes_immutable
        BEFORE UPDATE OR DELETE ON institution_control_changes
        FOR EACH ROW
        EXECUTE FUNCTION education_os_reject_control_change_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_control_changes_no_truncate
        BEFORE TRUNCATE ON institution_control_changes
        FOR EACH STATEMENT
        EXECUTE FUNCTION education_os_reject_control_change_mutation()
        """
    )

    _enable_control_rls(
        "institution_control_state",
        insert_allowed=True,
        update_allowed=True,
    )
    _enable_control_rls(
        "institution_policy_controls",
        insert_allowed=True,
        update_allowed=True,
    )
    _enable_control_rls(
        "institution_control_changes",
        insert_allowed=True,
        update_allowed=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index(
        "ix_m19_outbox_institution_created_id",
        table_name="outbox_events",
    )
    op.drop_index(
        "ix_m19_event_ledger_institution_position",
        table_name="event_ledger",
    )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_control_changes_no_truncate "
        "ON institution_control_changes"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_control_changes_immutable "
        "ON institution_control_changes"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS education_os_reject_control_change_mutation()"
    )

    op.drop_table("institution_control_changes")
    op.drop_table("institution_policy_controls")
    op.drop_table("institution_control_state")

    op.execute(
        """
        DROP FUNCTION IF EXISTS
        education_os_control_plane_has_permission(text)
        """
    )

    permission_rows = bind.execute(
        sa.text(
            """
            SELECT id, key
            FROM permissions
            WHERE key IN ('control_plane.view', 'control_plane.manage')
            """
        )
    ).all()
    for permission_id, _key in permission_rows:
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = :permission_id"
            ),
            {"permission_id": permission_id},
        )
    bind.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE key IN ('control_plane.view', 'control_plane.manage')
            """
        )
    )
