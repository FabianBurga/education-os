"""M21-C1 intervention actions and follow-ups.

Revision ID: 0022_m21_actions_followups
Revises: 0021_m21_intervention_core
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_m21_actions_followups"
down_revision: str | None = "0021_m21_intervention_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

M21_C_PERMISSIONS = (
    (
        "intervention.action.manage",
        "Create and manage authorized intervention actions.",
    ),
    (
        "intervention.followup.create",
        "Create authorized intervention follow-up records.",
    ),
)

MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")


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
            "INSERT INTO permissions (id, key, description) "
            "VALUES (:id, :key, :description)"
        ),
        {"id": permission_id, "key": key, "description": description},
    )
    return permission_id


def _grant_to_role_keys(bind, permission_id, role_keys: tuple[str, ...]) -> None:
    role_ids = bind.execute(
        sa.text("SELECT id FROM roles WHERE key = ANY(:role_keys)"),
        {"role_keys": list(role_keys)},
    ).scalars().all()
    for role_id in role_ids:
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def _has_permission(permission_key: str) -> str:
    return f"""
    EXISTS (
        SELECT 1
        FROM memberships m
        JOIN membership_roles mr ON mr.membership_id = m.id
        JOIN role_permissions rp ON rp.role_id = mr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE m.user_id = {USER_CTX}
          AND m.institution_id = {INST_CTX}
          AND m.status = 'ACTIVE'
          AND p.key IN ('{permission_key}', 'intervention.admin')
    )
    """


VISIBLE_PARENT_INTERVENTION = f"""
EXISTS (
    SELECT 1
    FROM interventions i
    WHERE i.id = intervention_id
      AND i.organization_id = {ORG_CTX}
      AND i.institution_id = {INST_CTX}
)
"""

HAS_RESTRICTED_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'student_timeline.read_restricted'
)
"""

HAS_CONFIDENTIAL_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'student_timeline.read_confidential'
)
"""


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M21_C_PERMISSIONS
    }
    for permission_id in permission_ids.values():
        _grant_to_role_keys(bind, permission_id, MANAGER_ROLE_KEYS)

    op.create_table(
        "intervention_actions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("intervention_id", UUID, nullable=False),
        sa.Column(
            "action_type",
            sa.String(40),
            nullable=False,
            server_default="REVIEW",
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("assigned_role_code", sa.String(60), nullable=True),
        sa.Column("assigned_user_id", UUID, nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", UUID, nullable=True),
        sa.Column("completion_note", sa.String(2000), nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=False),
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
            name="fk_intervention_actions_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["interventions.id"],
            name="fk_intervention_actions_intervention",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_actions_assigned_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_actions_completed_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_actions_created_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN "
            "('OPEN','ACKNOWLEDGED','IN_PROGRESS','COMPLETED','CANCELLED','OVERDUE')",
            name="ck_intervention_actions_status",
        ),
        sa.CheckConstraint(
            "(status <> 'COMPLETED') OR "
            "(completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL)",
            name="ck_intervention_actions_completed_requires_actor",
        ),
        sa.CheckConstraint(
            "(status <> 'ACKNOWLEDGED') OR acknowledged_at IS NOT NULL",
            name="ck_intervention_actions_acknowledged_timestamp",
        ),
        sa.CheckConstraint(
            "(status <> 'IN_PROGRESS') OR started_at IS NOT NULL",
            name="ck_intervention_actions_started_timestamp",
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_intervention_actions_title",
        ),
    )

    op.create_index(
        "ix_intervention_actions_intervention_status",
        "intervention_actions",
        ["intervention_id", "status"],
    )
    op.create_index(
        "ix_intervention_actions_assignee_status",
        "intervention_actions",
        ["assigned_user_id", "status"],
    )
    op.create_index(
        "ix_intervention_actions_due_status",
        "intervention_actions",
        ["due_at", "status"],
    )

    op.create_table(
        "intervention_followups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("intervention_id", UUID, nullable=False),
        sa.Column("followup_type", sa.String(50), nullable=False),
        sa.Column(
            "sensitivity",
            sa.String(20),
            nullable=False,
            server_default="GENERAL",
        ),
        sa.Column("note", sa.String(4000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_intervention_followups_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["interventions.id"],
            name="fk_intervention_followups_intervention",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_followups_created_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "followup_type IN "
            "('MEETING','PHONE_CALL','FAMILY_CONTACT','STUDENT_CONVERSATION',"
            "'TEACHER_REVIEW','ACADEMIC_REVIEW','ATTENDANCE_REVIEW',"
            "'PSYCHOLOGY_SESSION','REFERRAL','OTHER')",
            name="ck_intervention_followups_type",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_intervention_followups_sensitivity",
        ),
        sa.CheckConstraint(
            "length(trim(note)) > 0",
            name="ck_intervention_followups_note",
        ),
    )

    op.create_index(
        "ix_intervention_followups_intervention_observed",
        "intervention_followups",
        ["intervention_id", "observed_at"],
    )
    op.create_index(
        "ix_intervention_followups_sensitivity_observed",
        "intervention_followups",
        ["sensitivity", "observed_at"],
    )

    op.execute('ALTER TABLE "intervention_actions" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "intervention_actions" FORCE ROW LEVEL SECURITY')
    op.execute(
        'GRANT SELECT, INSERT, UPDATE ON "intervention_actions" TO education_app'
    )

    op.execute(
        f"""
        CREATE POLICY intervention_actions_select
        ON intervention_actions
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_actions_insert
        ON intervention_actions
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
            AND ({_has_permission("intervention.action.manage")})
            AND created_by_user_id = {USER_CTX}
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_actions_update
        ON intervention_actions
        FOR UPDATE TO education_app
        USING (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
            AND ({_has_permission("intervention.action.manage")})
        )
        WITH CHECK (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
            AND ({_has_permission("intervention.action.manage")})
        )
        """
    )

    op.execute('ALTER TABLE "intervention_followups" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "intervention_followups" FORCE ROW LEVEL SECURITY')
    op.execute(
        'GRANT SELECT, INSERT ON "intervention_followups" TO education_app'
    )

    op.execute(
        f"""
        CREATE POLICY intervention_followups_select
        ON intervention_followups
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
            AND (
                sensitivity = 'GENERAL'
                OR (
                    sensitivity = 'RESTRICTED'
                    AND ({HAS_RESTRICTED_READ})
                )
                OR (
                    sensitivity = 'CONFIDENTIAL'
                    AND ({HAS_CONFIDENTIAL_READ})
                )
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_followups_insert
        ON intervention_followups
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND ({VISIBLE_PARENT_INTERVENTION})
            AND ({_has_permission("intervention.followup.create")})
            AND created_by_user_id = {USER_CTX}
            AND (
                sensitivity = 'GENERAL'
                OR (
                    sensitivity = 'RESTRICTED'
                    AND ({HAS_RESTRICTED_READ})
                )
                OR (
                    sensitivity = 'CONFIDENTIAL'
                    AND ({HAS_CONFIDENTIAL_READ})
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS intervention_followups_insert '
        'ON intervention_followups'
    )
    op.execute(
        'DROP POLICY IF EXISTS intervention_followups_select '
        'ON intervention_followups'
    )
    op.drop_table("intervention_followups")

    op.execute(
        'DROP POLICY IF EXISTS intervention_actions_update '
        'ON intervention_actions'
    )
    op.execute(
        'DROP POLICY IF EXISTS intervention_actions_insert '
        'ON intervention_actions'
    )
    op.execute(
        'DROP POLICY IF EXISTS intervention_actions_select '
        'ON intervention_actions'
    )
    op.drop_table("intervention_actions")

    bind = op.get_bind()
    for key, _description in M21_C_PERMISSIONS:
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
                sa.text("DELETE FROM permissions WHERE id = :permission_id"),
                {"permission_id": permission_id},
            )