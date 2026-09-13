"""M21 Student Timeline data model.

Revision ID: 0020_m21
Revises: 0019_m20
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_m21"
down_revision: str | None = "0019_m20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

M21_TIMELINE_PERMISSIONS = (
    ("student_timeline.read", "View authorized student longitudinal timeline entries."),
    ("student_timeline.read_restricted", "View restricted student timeline entries."),
    ("student_timeline.read_confidential", "View confidential student timeline entries."),
)

GENERAL_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR", "TEACHER")
RESTRICTED_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")
CONFIDENTIAL_ROLE_KEYS = ("SYSTEM_ADMIN",)

HAS_BASE_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'student_timeline.read'
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

IS_PRIVILEGED = f"""
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
      AND e.student_profile_id = student_timeline_entries.student_profile_id
      AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
      AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
)
"""

CAN_PROJECT = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'admin.console.access'
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
        for key, description in M21_TIMELINE_PERMISSIONS
    }
    _grant_to_role_keys(bind, permission_ids["student_timeline.read"], GENERAL_ROLE_KEYS)
    _grant_to_role_keys(
        bind,
        permission_ids["student_timeline.read_restricted"],
        RESTRICTED_ROLE_KEYS,
    )
    _grant_to_role_keys(
        bind,
        permission_ids["student_timeline.read_confidential"],
        CONFIDENTIAL_ROLE_KEYS,
    )

    op.create_table(
        "student_timeline_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("ledger_event_id", UUID, nullable=False),
        sa.Column("ledger_position", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(180), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("importance", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default="GENERAL"),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("summary", sa.String(1200), nullable=True),
        sa.Column("source_aggregate_type", sa.String(100), nullable=False),
        sa.Column("source_aggregate_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("causation_id", UUID, nullable=True),
        sa.Column("context_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_student_timeline_entries_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id"],
            ["student_profiles.id"],
            name="fk_student_timeline_entries_student",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_event_id"],
            ["event_ledger.id"],
            name="fk_student_timeline_entries_ledger_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_accounts.id"],
            name="fk_student_timeline_entries_actor",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("ledger_position > 0", name="ck_student_timeline_position"),
        sa.CheckConstraint("event_version >= 1", name="ck_student_timeline_event_version"),
        sa.CheckConstraint(
            "category IN ('ENROLLMENT','ATTENDANCE','ACADEMIC','SIGNAL',"
            "'INTERVENTION','ACTION','FOLLOW_UP','COMMUNICATION','OUTCOME','SYSTEM')",
            name="ck_student_timeline_category",
        ),
        sa.CheckConstraint(
            "importance IN ('LOW','NORMAL','HIGH','CRITICAL')",
            name="ck_student_timeline_importance",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_student_timeline_sensitivity",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "ledger_event_id",
            name="uq_student_timeline_inst_ledger_event",
        ),
    )

    op.create_index("ix_student_timeline_organization", "student_timeline_entries", ["organization_id"])
    op.create_index("ix_student_timeline_institution", "student_timeline_entries", ["institution_id"])
    op.create_index("ix_student_timeline_student_occurred", "student_timeline_entries", ["student_profile_id", "occurred_at"])
    op.create_index("ix_student_timeline_student_category_occurred", "student_timeline_entries", ["student_profile_id", "category", "occurred_at"])
    op.create_index("ix_student_timeline_ledger_position", "student_timeline_entries", ["ledger_position"])
    op.create_index("ix_student_timeline_correlation", "student_timeline_entries", ["correlation_id"])

    op.execute('ALTER TABLE "student_timeline_entries" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "student_timeline_entries" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT ON "student_timeline_entries" TO education_app')

    op.execute(
        f"""
        CREATE POLICY student_timeline_entries_select
        ON student_timeline_entries
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND (
                (
                    sensitivity = 'GENERAL'
                    AND ({HAS_BASE_READ})
                    AND (({IS_PRIVILEGED}) OR ({TEACHER_STUDENT_SCOPE}))
                )
                OR (
                    sensitivity = 'RESTRICTED'
                    AND ({HAS_RESTRICTED_READ})
                    AND ({IS_PRIVILEGED})
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
        CREATE POLICY student_timeline_entries_insert
        ON student_timeline_entries
        FOR INSERT TO education_app
        WITH CHECK ({TENANT} AND ({CAN_PROJECT}))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("student_timeline_entries")

    permission_ids = []
    for key, _description in M21_TIMELINE_PERMISSIONS:
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

    for key, _description in M21_TIMELINE_PERMISSIONS:
        bind.execute(
            sa.text(
                "DELETE FROM permissions p WHERE p.key = :key "
                "AND NOT EXISTS (SELECT 1 FROM role_permissions rp "
                "WHERE rp.permission_id = p.id)"
            ),
            {"key": key},
        )
