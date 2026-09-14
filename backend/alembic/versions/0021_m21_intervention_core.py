"""M21 Intervention Core data model.

Revision ID: 0021_m21_intervention_core
Revises: 0020_m21
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021_m21_intervention_core"
down_revision: str | None = "0020_m21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

M21_INTERVENTION_PERMISSIONS = (
    ("intervention.read", "View authorized institutional interventions."),
    ("intervention.create", "Create institutional interventions."),
    ("intervention.update", "Update intervention workflow state and metadata."),
    ("intervention.assign", "Assign institutional intervention ownership."),
    ("intervention.resolve", "Resolve institutional interventions."),
    ("intervention.close", "Close institutional interventions with an outcome."),
    ("intervention.admin", "Perform privileged intervention administration."),
)

MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")
READ_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR", "TEACHER")

HAS_INTERVENTION_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'intervention.read'
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

IS_MANAGER = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN roles r ON r.id = mr.role_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND r.key IN ('SYSTEM_ADMIN', 'RECTOR', 'ACADEMIC_COORDINATOR')
)
"""

TEACHER_STUDENT_SCOPE = f"""
EXISTS (
    SELECT 1
    FROM user_accounts ua
    JOIN staff_profiles sp
      ON sp.person_id = ua.person_id
     AND sp.institution_id = {INST_CTX}
     AND sp.status = 'ACTIVE'
    JOIN teaching_assignments ta
      ON ta.staff_profile_id = sp.id
     AND ta.institution_id = {INST_CTX}
    JOIN course_offerings co
      ON co.id = ta.course_offering_id
     AND co.institution_id = {INST_CTX}
     AND co.status = 'ACTIVE'
    JOIN student_section_assignments ssa
      ON ssa.section_id = co.section_id
     AND ssa.institution_id = {INST_CTX}
     AND ssa.status = 'ACTIVE'
    JOIN enrollments e
      ON e.id = ssa.enrollment_id
     AND e.institution_id = {INST_CTX}
    WHERE ua.id = {USER_CTX}
      AND ua.is_active = true
      AND e.student_profile_id = interventions.student_profile_id
      AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
      AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
)
"""

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


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M21_INTERVENTION_PERMISSIONS
    }
    _grant_to_role_keys(bind, permission_ids["intervention.read"], READ_ROLE_KEYS)
    for key in (
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
        "intervention.admin",
    ):
        _grant_to_role_keys(bind, permission_ids[key], MANAGER_ROLE_KEYS)

    op.create_table(
        "interventions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("section_id", UUID, nullable=True),
        sa.Column("intervention_type", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="GENERAL"),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("objective", sa.String(2000), nullable=True),
        sa.Column("origin_type", sa.String(30), nullable=False),
        sa.Column("opened_by_user_id", UUID, nullable=False),
        sa.Column("assigned_role_code", sa.String(60), nullable=True),
        sa.Column("assigned_user_id", UUID, nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_type", sa.String(30), nullable=True),
        sa.Column("outcome_summary", sa.String(2000), nullable=True),
        sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_recorded_by_user_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_interventions_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["student_profiles.id"],
            name="fk_interventions_student",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id"],
            ["academic_periods.id"],
            name="fk_interventions_academic_period",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name="fk_interventions_section",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_user_id"],
            ["user_accounts.id"],
            name="fk_interventions_opened_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["user_accounts.id"],
            name="fk_interventions_assigned_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["outcome_recorded_by_user_id"],
            ["user_accounts.id"],
            name="fk_interventions_outcome_actor",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_interventions_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','MONITORING','RESOLVED','CLOSED','CANCELLED')",
            name="ck_interventions_status",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_interventions_sensitivity",
        ),
        sa.CheckConstraint(
            "origin_type IN ('HUMAN','SIGNAL','LEGACY_CASE','SYSTEM_SUGGESTION')",
            name="ck_interventions_origin_type",
        ),
        sa.CheckConstraint(
            "outcome_type IS NULL OR outcome_type IN "
            "('IMPROVED','STABLE','NO_CHANGE','WORSENED','REFERRED','TRANSFERRED','NOT_ASSESSABLE')",
            name="ck_interventions_outcome_type",
        ),
        sa.CheckConstraint(
            "(status <> 'CLOSED') OR "
            "(closed_at IS NOT NULL AND outcome_type IS NOT NULL "
            "AND outcome_summary IS NOT NULL "
            "AND outcome_recorded_at IS NOT NULL "
            "AND outcome_recorded_by_user_id IS NOT NULL)",
            name="ck_interventions_closed_requires_outcome",
        ),
    )

    op.create_index("ix_interventions_organization", "interventions", ["organization_id"])
    op.create_index("ix_interventions_institution", "interventions", ["institution_id"])
    op.create_index(
        "ix_interventions_student_status",
        "interventions",
        ["student_profile_id", "status"],
    )
    op.create_index(
        "ix_interventions_assigned_user_status",
        "interventions",
        ["assigned_user_id", "status"],
    )
    op.create_index(
        "ix_interventions_status_target",
        "interventions",
        ["status", "target_at"],
    )
    op.create_index(
        "ix_interventions_opened_at",
        "interventions",
        ["opened_at"],
    )

    op.create_table(
        "intervention_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("intervention_id", UUID, nullable=False),
        sa.Column("link_type", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_intervention_links_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["intervention_id"],
            ["interventions.id"],
            name="fk_intervention_links_intervention",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_links_created_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "link_type IN ('ORIGIN','EVIDENCE','RELATED','LEGACY_CASE')",
            name="ck_intervention_links_type",
        ),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="ck_intervention_links_entity_type",
        ),
        sa.UniqueConstraint(
            "intervention_id",
            "link_type",
            "entity_type",
            "entity_id",
            name="uq_intervention_links_identity",
        ),
    )

    op.create_index(
        "ix_intervention_links_intervention",
        "intervention_links",
        ["intervention_id"],
    )
    op.create_index(
        "ix_intervention_links_entity",
        "intervention_links",
        ["entity_type", "entity_id"],
    )

    op.execute('ALTER TABLE "interventions" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "interventions" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT, UPDATE ON "interventions" TO education_app')

    op.execute(
        f"""
        CREATE POLICY interventions_select
        ON interventions
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND ({HAS_INTERVENTION_READ})
            AND (
                (
                    sensitivity = 'GENERAL'
                    AND (({IS_MANAGER}) OR ({TEACHER_STUDENT_SCOPE}))
                )
                OR (
                    sensitivity = 'RESTRICTED'
                    AND ({IS_MANAGER})
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
        CREATE POLICY interventions_insert
        ON interventions
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND ({_has_permission("intervention.create")})
            AND opened_by_user_id = {USER_CTX}
        )
        """
    )

    op.execute(
        f"""
        CREATE POLICY interventions_update
        ON interventions
        FOR UPDATE TO education_app
        USING (
            {TENANT}
            AND (
                ({_has_permission("intervention.update")})
                OR ({_has_permission("intervention.assign")})
                OR ({_has_permission("intervention.resolve")})
                OR ({_has_permission("intervention.close")})
            )
        )
        WITH CHECK (
            {TENANT}
            AND (
                ({_has_permission("intervention.update")})
                OR ({_has_permission("intervention.assign")})
                OR ({_has_permission("intervention.resolve")})
                OR ({_has_permission("intervention.close")})
            )
        )
        """
    )

    op.execute('ALTER TABLE "intervention_links" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "intervention_links" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT ON "intervention_links" TO education_app')

    op.execute(
        f"""
        CREATE POLICY intervention_links_select
        ON intervention_links
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND EXISTS (
                SELECT 1
                FROM interventions i
                WHERE i.id = intervention_links.intervention_id
                  AND i.institution_id = {INST_CTX}
                  AND i.organization_id = {ORG_CTX}
            )
        )
        """
    )

    op.execute(
        f"""
        CREATE POLICY intervention_links_insert
        ON intervention_links
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND created_by_user_id = {USER_CTX}
            AND (
                ({_has_permission("intervention.create")})
                OR ({_has_permission("intervention.update")})
            )
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_table("intervention_links")
    op.drop_table("interventions")

    permission_ids = []
    for key, _description in M21_INTERVENTION_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is not None:
            permission_ids.append(permission_id)

    for permission_id in permission_ids:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )

    for key, _description in M21_INTERVENTION_PERMISSIONS:
        bind.execute(
            sa.text(
                "DELETE FROM permissions p WHERE p.key = :key "
                "AND NOT EXISTS (SELECT 1 FROM role_permissions rp "
                "WHERE rp.permission_id = p.id)"
            ),
            {"key": key},
        )