"""M3 attendance and grades.

Revision ID: 0004_m3
Revises: 0003_m2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_m3"
down_revision: str | None = "0003_m2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

M3_TABLES = (
    "attendance_codes",
    "class_sessions",
    "attendance_records",
    "grading_periods",
    "grading_scales",
    "grading_scale_bands",
    "assessment_categories",
    "assessments",
    "grade_entries",
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


def upgrade() -> None:
    # M2 hardening needed by M3 composite relationships.
    op.create_unique_constraint(
        "uq_student_section_assignments_id_inst",
        "student_section_assignments",
        ["id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_student_section_assignments_id_section_inst",
        "student_section_assignments",
        ["id", "section_id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_schedule_slots_id_course_inst",
        "schedule_slots",
        ["id", "course_offering_id", "institution_id"],
    )
    op.create_unique_constraint(
        "uq_course_offerings_id_section_inst",
        "course_offerings",
        ["id", "section_id", "institution_id"],
    )

    op.create_table(
        "attendance_codes",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("semantic", sa.String(20), nullable=False),
        sa.Column("counts_as_present", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("counts_as_absent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("counts_as_late", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_attendance_codes_tenant"),
        sa.CheckConstraint(
            "semantic IN ('PRESENT','ABSENT','LATE','EXCUSED','REMOTE','OTHER')",
            name="ck_attendance_codes_semantic",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_attendance_codes_status",
        ),
        sa.UniqueConstraint("institution_id", "code", name="uq_attendance_codes_inst_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_attendance_codes_id_inst"),
    )

    op.create_table(
        "class_sessions",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("course_offering_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("schedule_slot_id", UUID, nullable=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_class_sessions_tenant"),
        sa.ForeignKeyConstraint(
            ["course_offering_id", "section_id", "institution_id"],
            ["course_offerings.id", "course_offerings.section_id", "course_offerings.institution_id"],
            name="fk_class_sessions_course_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["schedule_slot_id", "course_offering_id", "institution_id"],
            ["schedule_slots.id", "schedule_slots.course_offering_id", "schedule_slots.institution_id"],
            name="fk_class_sessions_slot_course_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_class_sessions_time_range"),
        sa.CheckConstraint(
            "status IN ('OPEN','CLOSED','CANCELLED')",
            name="ck_class_sessions_status",
        ),
        sa.UniqueConstraint(
            "course_offering_id",
            "session_date",
            "starts_at",
            name="uq_class_sessions_course_date_start",
        ),
        sa.UniqueConstraint(
            "id",
            "section_id",
            "institution_id",
            name="uq_class_sessions_id_section_inst",
        ),
    )

    op.create_table(
        "attendance_records",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("class_session_id", UUID, nullable=False),
        sa.Column("student_section_assignment_id", UUID, nullable=False),
        sa.Column("attendance_code_id", UUID, nullable=False),
        sa.Column("minutes_late", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(500), nullable=True),
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
        tenant_constraint("fk_attendance_records_tenant"),
        sa.ForeignKeyConstraint(
            ["class_session_id", "section_id", "institution_id"],
            ["class_sessions.id", "class_sessions.section_id", "class_sessions.institution_id"],
            name="fk_attendance_records_session_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_section_assignment_id", "section_id", "institution_id"],
            [
                "student_section_assignments.id",
                "student_section_assignments.section_id",
                "student_section_assignments.institution_id",
            ],
            name="fk_attendance_records_student_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attendance_code_id", "institution_id"],
            ["attendance_codes.id", "attendance_codes.institution_id"],
            name="fk_attendance_records_code_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "minutes_late >= 0 AND minutes_late <= 1440",
            name="ck_attendance_records_minutes_late",
        ),
        sa.UniqueConstraint(
            "class_session_id",
            "student_section_assignment_id",
            name="uq_attendance_records_session_student",
        ),
    )

    op.create_table(
        "grading_periods",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("academic_period_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_grading_periods_tenant"),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_grading_periods_academic_period_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_grading_periods_dates"),
        sa.CheckConstraint("sequence >= 1", name="ck_grading_periods_sequence"),
        sa.CheckConstraint(
            "status IN ('PLANNED','ACTIVE','CLOSED')",
            name="ck_grading_periods_status",
        ),
        sa.UniqueConstraint(
            "academic_period_id",
            "code",
            name="uq_grading_periods_period_code",
        ),
        sa.UniqueConstraint("id", "institution_id", name="uq_grading_periods_id_inst"),
    )

    op.create_table(
        "grading_scales",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("minimum_score", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("maximum_score", sa.Numeric(8, 3), nullable=False, server_default="10"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_grading_scales_tenant"),
        sa.CheckConstraint(
            "maximum_score > minimum_score",
            name="ck_grading_scales_range",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_grading_scales_status",
        ),
        sa.UniqueConstraint("institution_id", "code", name="uq_grading_scales_inst_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_grading_scales_id_inst"),
    )

    op.create_table(
        "grading_scale_bands",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("grading_scale_id", UUID, nullable=False),
        sa.Column("minimum_score", sa.Numeric(8, 3), nullable=False),
        sa.Column("maximum_score", sa.Numeric(8, 3), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("result_code", sa.String(40), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_grading_scale_bands_tenant"),
        sa.ForeignKeyConstraint(
            ["grading_scale_id", "institution_id"],
            ["grading_scales.id", "grading_scales.institution_id"],
            name="fk_grading_scale_bands_scale_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "maximum_score >= minimum_score",
            name="ck_grading_scale_bands_range",
        ),
    )

    op.create_table(
        "assessment_categories",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("course_offering_id", UUID, nullable=False),
        sa.Column("grading_period_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("weight_percent", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_assessment_categories_tenant"),
        sa.ForeignKeyConstraint(
            ["course_offering_id", "section_id", "institution_id"],
            ["course_offerings.id", "course_offerings.section_id", "course_offerings.institution_id"],
            name="fk_assessment_categories_course_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grading_period_id", "institution_id"],
            ["grading_periods.id", "grading_periods.institution_id"],
            name="fk_assessment_categories_period_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "weight_percent >= 0 AND weight_percent <= 100",
            name="ck_assessment_categories_weight",
        ),
        sa.UniqueConstraint(
            "course_offering_id",
            "grading_period_id",
            "code",
            name="uq_assessment_categories_course_period_code",
        ),
        sa.UniqueConstraint(
            "id",
            "course_offering_id",
            "institution_id",
            name="uq_assessment_categories_id_course_inst",
        ),
    )

    op.create_table(
        "assessments",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("course_offering_id", UUID, nullable=False),
        sa.Column("grading_period_id", UUID, nullable=False),
        sa.Column("assessment_category_id", UUID, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("max_score", sa.Numeric(8, 3), nullable=False, server_default="10"),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_assessments_tenant"),
        sa.ForeignKeyConstraint(
            ["course_offering_id", "section_id", "institution_id"],
            ["course_offerings.id", "course_offerings.section_id", "course_offerings.institution_id"],
            name="fk_assessments_course_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grading_period_id", "institution_id"],
            ["grading_periods.id", "grading_periods.institution_id"],
            name="fk_assessments_period_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_category_id", "course_offering_id", "institution_id"],
            [
                "assessment_categories.id",
                "assessment_categories.course_offering_id",
                "assessment_categories.institution_id",
            ],
            name="fk_assessments_category_course_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("max_score > 0", name="ck_assessments_max_score"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','CLOSED','ARCHIVED')",
            name="ck_assessments_status",
        ),
        sa.UniqueConstraint(
            "course_offering_id",
            "grading_period_id",
            "code",
            name="uq_assessments_course_period_code",
        ),
        sa.UniqueConstraint(
            "id",
            "section_id",
            "institution_id",
            name="uq_assessments_id_section_inst",
        ),
    )

    op.create_table(
        "grade_entries",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("section_id", UUID, nullable=False),
        sa.Column("assessment_id", UUID, nullable=False),
        sa.Column("student_section_assignment_id", UUID, nullable=False),
        sa.Column("score", sa.Numeric(8, 3), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("feedback", sa.String(1000), nullable=True),
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
        tenant_constraint("fk_grade_entries_tenant"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "section_id", "institution_id"],
            ["assessments.id", "assessments.section_id", "assessments.institution_id"],
            name="fk_grade_entries_assessment_section_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_section_assignment_id", "section_id", "institution_id"],
            [
                "student_section_assignments.id",
                "student_section_assignments.section_id",
                "student_section_assignments.institution_id",
            ],
            name="fk_grade_entries_student_section_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("score IS NULL OR score >= 0", name="ck_grade_entries_score"),
        sa.CheckConstraint(
            "status IN ('PENDING','GRADED','MISSING','EXCUSED')",
            name="ck_grade_entries_status",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "student_section_assignment_id",
            name="uq_grade_entries_assessment_student",
        ),
    )

    for table in M3_TABLES:
        op.create_index(f"ix_{table}_organization", table, ["organization_id"])
        op.create_index(f"ix_{table}_institution", table, ["institution_id"])
        enable_rls(table)


def downgrade() -> None:
    for table in reversed(M3_TABLES):
        op.drop_table(table)

    op.drop_constraint(
        "uq_course_offerings_id_section_inst",
        "course_offerings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_schedule_slots_id_course_inst",
        "schedule_slots",
        type_="unique",
    )
    op.drop_constraint(
        "uq_student_section_assignments_id_section_inst",
        "student_section_assignments",
        type_="unique",
    )
    op.drop_constraint(
        "uq_student_section_assignments_id_inst",
        "student_section_assignments",
        type_="unique",
    )
