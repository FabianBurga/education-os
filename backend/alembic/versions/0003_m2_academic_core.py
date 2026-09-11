"""M2 academic core and tenant-safe relations.

Revision ID: 0003_m2
Revises: 0002_m1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_m2"
down_revision: str | None = "0002_m1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

M2_TABLES = (
    "academic_levels",
    "grade_levels",
    "subjects",
    "sections",
    "curriculum_plans",
    "curriculum_subjects",
    "course_offerings",
    "teaching_assignments",
    "student_section_assignments",
    "schedule_slots",
)

TENANT_EXPR = """
organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
"""


def tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
    ]


def tenant_constraint(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["institution_id", "organization_id"],
        ["institutions.id", "institutions.organization_id"],
        name=name,
        ondelete="RESTRICT",
    )


def enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_isolation
        ON "{table}"
        FOR ALL
        TO education_app
        USING ({TENANT_EXPR})
        WITH CHECK ({TENANT_EXPR})
        """
    )
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO education_app')


def harden_m1_relations() -> None:
    op.create_unique_constraint(
        "uq_institutions_id_org",
        "institutions",
        ["id", "organization_id"],
    )
    op.create_unique_constraint("uq_persons_id_org", "persons", ["id", "organization_id"])
    op.create_unique_constraint("uq_campuses_id_inst", "campuses", ["id", "institution_id"])
    op.create_unique_constraint(
        "uq_academic_periods_id_inst",
        "academic_periods",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_student_profiles_id_inst",
        "student_profiles",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_guardian_profiles_id_inst",
        "guardian_profiles",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_staff_profiles_id_inst",
        "staff_profiles",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_family_households_id_inst",
        "family_households",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_enrollments_id_inst",
        "enrollments",
        ["id", "institution_id"],
    )

    tenant_tables = (
        "student_profiles",
        "guardian_profiles",
        "staff_profiles",
        "family_households",
        "family_members",
        "student_guardian_relationships",
        "academic_periods",
        "enrollments",
    )
    for table in tenant_tables:
        op.create_foreign_key(
            f"fk_{table}_tenant_pair",
            table,
            "institutions",
            ["institution_id", "organization_id"],
            ["id", "organization_id"],
            ondelete="RESTRICT",
        )

    for table in ("student_profiles", "guardian_profiles", "staff_profiles"):
        op.create_foreign_key(
            f"fk_{table}_person_org",
            table,
            "persons",
            ["person_id", "organization_id"],
            ["id", "organization_id"],
            ondelete="RESTRICT",
        )

    op.create_foreign_key(
        "fk_family_members_person_org",
        "family_members",
        "persons",
        ["person_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_family_members_family_inst",
        "family_members",
        "family_households",
        ["family_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_student_guardian_student_inst",
        "student_guardian_relationships",
        "student_profiles",
        ["student_profile_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_student_guardian_guardian_inst",
        "student_guardian_relationships",
        "guardian_profiles",
        ["guardian_profile_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_enrollments_student_inst",
        "enrollments",
        "student_profiles",
        ["student_profile_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_enrollments_period_inst",
        "enrollments",
        "academic_periods",
        ["academic_period_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_enrollments_campus_inst",
        "enrollments",
        "campuses",
        ["campus_id", "institution_id"],
        ["id", "institution_id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    harden_m1_relations()

    op.create_table(
        "academic_levels",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_academic_levels_tenant"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_academic_levels_status",
        ),
        sa.UniqueConstraint("institution_id", "code", name="uq_academic_levels_inst_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_academic_levels_id_inst"),
    )

    op.create_table(
        "grade_levels",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_level_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_grade_levels_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_level_id", "institution_id"],
            ["academic_levels.id", "academic_levels.institution_id"],
            name="fk_grade_levels_level_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_grade_levels_status",
        ),
        sa.UniqueConstraint("institution_id", "code", name="uq_grade_levels_inst_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_grade_levels_id_inst"),
    )

    op.create_table(
        "subjects",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("area", sa.String(120), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_subjects_tenant"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_subjects_status",
        ),
        sa.UniqueConstraint("institution_id", "code", name="uq_subjects_inst_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_subjects_id_inst"),
    )

    op.create_table(
        "sections",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_period_id", UUID, nullable=False),
        sa.Column("campus_id", UUID, nullable=False),
        sa.Column("grade_level_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("shift", sa.String(20), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_sections_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_sections_period_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["campus_id", "institution_id"],
            ["campuses.id", "campuses.institution_id"],
            name="fk_sections_campus_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["grade_level_id", "institution_id"],
            ["grade_levels.id", "grade_levels.institution_id"],
            name="fk_sections_grade_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("capacity > 0", name="ck_sections_capacity"),
        sa.CheckConstraint(
            "shift IS NULL OR shift IN ('MORNING','AFTERNOON','EVENING','FULL_DAY')",
            name="ck_sections_shift",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_sections_status",
        ),
        sa.UniqueConstraint(
            "academic_period_id",
            "campus_id",
            "grade_level_id",
            "code",
            name="uq_sections_period_campus_grade_code",
        ),
        sa.UniqueConstraint("id", "institution_id", name="uq_sections_id_inst"),
    )

    op.create_table(
        "curriculum_plans",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_period_id", UUID, nullable=False),
        sa.Column("grade_level_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_curriculum_plans_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_curriculum_plans_period_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["grade_level_id", "institution_id"],
            ["grade_levels.id", "grade_levels.institution_id"],
            name="fk_curriculum_plans_grade_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ARCHIVED')",
            name="ck_curriculum_plans_status",
        ),
        sa.UniqueConstraint(
            "academic_period_id",
            "grade_level_id",
            "code",
            name="uq_curriculum_plans_period_grade_code",
        ),
        sa.UniqueConstraint("id", "institution_id", name="uq_curriculum_plans_id_inst"),
    )

    op.create_table(
        "curriculum_subjects",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("curriculum_plan_id", UUID, nullable=False),
        sa.Column("subject_id", UUID, nullable=False),
        sa.Column("weekly_periods", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_curriculum_subjects_tenant"),
        sa.ForeignKeyConstraint(
            ["curriculum_plan_id", "institution_id"],
            ["curriculum_plans.id", "curriculum_plans.institution_id"],
            name="fk_curriculum_subjects_plan_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "institution_id"],
            ["subjects.id", "subjects.institution_id"],
            name="fk_curriculum_subjects_subject_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "weekly_periods >= 0 AND weekly_periods <= 60",
            name="ck_curriculum_subjects_weekly_periods",
        ),
        sa.UniqueConstraint(
            "curriculum_plan_id",
            "subject_id",
            name="uq_curriculum_subjects_plan_subject",
        ),
        sa.UniqueConstraint("id", "institution_id", name="uq_curriculum_subjects_id_inst"),
    )

    op.create_table(
        "course_offerings",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_period_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("subject_id", UUID, nullable=False),
        sa.Column("curriculum_subject_id", UUID, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_course_offerings_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_course_offerings_period_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "institution_id"],
            ["sections.id", "sections.institution_id"],
            name="fk_course_offerings_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "institution_id"],
            ["subjects.id", "subjects.institution_id"],
            name="fk_course_offerings_subject_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_subject_id", "institution_id"],
            ["curriculum_subjects.id", "curriculum_subjects.institution_id"],
            name="fk_course_offerings_curriculum_subject_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_course_offerings_status",
        ),
        sa.UniqueConstraint(
            "section_id",
            "subject_id",
            name="uq_course_offerings_section_subject",
        ),
        sa.UniqueConstraint("id", "institution_id", name="uq_course_offerings_id_inst"),
    )

    op.create_table(
        "teaching_assignments",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("course_offering_id", UUID, nullable=False),
        sa.Column("staff_profile_id", UUID, nullable=False),
        sa.Column("assignment_role", sa.String(20), nullable=False, server_default="LEAD"),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_teaching_assignments_tenant"),
        sa.ForeignKeyConstraint(
            ["course_offering_id", "institution_id"],
            ["course_offerings.id", "course_offerings.institution_id"],
            name="fk_teaching_assignments_course_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["staff_profile_id", "institution_id"],
            ["staff_profiles.id", "staff_profiles.institution_id"],
            name="fk_teaching_assignments_staff_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assignment_role IN ('LEAD','CO_TEACHER','SUPPORT')",
            name="ck_teaching_assignments_role",
        ),
        sa.CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR ends_on >= starts_on",
            name="ck_teaching_assignments_dates",
        ),
        sa.UniqueConstraint(
            "course_offering_id",
            "staff_profile_id",
            name="uq_teaching_assignments_course_staff",
        ),
    )

    op.create_table(
        "student_section_assignments",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_period_id", UUID, nullable=False),
        sa.Column("enrollment_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("assigned_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_student_section_assignments_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_student_section_assignments_period_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "institution_id"],
            ["enrollments.id", "enrollments.institution_id"],
            name="fk_student_section_assignments_enrollment_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "institution_id"],
            ["sections.id", "sections.institution_id"],
            name="fk_student_section_assignments_section_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','TRANSFERRED','WITHDRAWN')",
            name="ck_student_section_assignments_status",
        ),
        sa.CheckConstraint(
            "ended_on IS NULL OR ended_on >= assigned_on",
            name="ck_student_section_assignments_dates",
        ),
    )
    op.create_index(
        "uq_student_section_active_enrollment",
        "student_section_assignments",
        ["enrollment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "schedule_slots",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("course_offering_id", UUID, nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("room_label", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_schedule_slots_tenant"),
        sa.ForeignKeyConstraint(
            ["course_offering_id", "institution_id"],
            ["course_offerings.id", "course_offerings.institution_id"],
            name="fk_schedule_slots_course_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_schedule_slots_weekday"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_schedule_slots_time_range"),
        sa.UniqueConstraint(
            "course_offering_id",
            "weekday",
            "starts_at",
            name="uq_schedule_slots_course_day_start",
        ),
    )

    for table in M2_TABLES:
        op.create_index(f"ix_{table}_organization", table, ["organization_id"])
        op.create_index(f"ix_{table}_institution", table, ["institution_id"])
        enable_rls(table)


def downgrade() -> None:
    for table in reversed(M2_TABLES):
        op.drop_table(table)

    m1_fk_names = [
        ("enrollments", "fk_enrollments_campus_inst"),
        ("enrollments", "fk_enrollments_period_inst"),
        ("enrollments", "fk_enrollments_student_inst"),
        ("student_guardian_relationships", "fk_student_guardian_guardian_inst"),
        ("student_guardian_relationships", "fk_student_guardian_student_inst"),
        ("family_members", "fk_family_members_family_inst"),
        ("family_members", "fk_family_members_person_org"),
        ("staff_profiles", "fk_staff_profiles_person_org"),
        ("guardian_profiles", "fk_guardian_profiles_person_org"),
        ("student_profiles", "fk_student_profiles_person_org"),
    ]
    for table, constraint in m1_fk_names:
        op.drop_constraint(constraint, table, type_="foreignkey")

    tenant_tables = (
        "student_profiles",
        "guardian_profiles",
        "staff_profiles",
        "family_households",
        "family_members",
        "student_guardian_relationships",
        "academic_periods",
        "enrollments",
    )
    for table in tenant_tables:
        op.drop_constraint(f"fk_{table}_tenant_pair", table, type_="foreignkey")

    unique_constraints = [
        ("enrollments", "uq_enrollments_id_inst"),
        ("family_households", "uq_family_households_id_inst"),
        ("staff_profiles", "uq_staff_profiles_id_inst"),
        ("guardian_profiles", "uq_guardian_profiles_id_inst"),
        ("student_profiles", "uq_student_profiles_id_inst"),
        ("academic_periods", "uq_academic_periods_id_inst"),
        ("campuses", "uq_campuses_id_inst"),
        ("persons", "uq_persons_id_org"),
        ("institutions", "uq_institutions_id_org"),
    ]
    for table, constraint in unique_constraints:
        op.drop_constraint(constraint, table, type_="unique")
