"""M1 students, families and enrollment.

Revision ID: 0002_m1
Revises: 0001_m0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m1"
down_revision: str | None = "0001_m0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

M1_TABLES = (
    "student_profiles",
    "guardian_profiles",
    "staff_profiles",
    "family_households",
    "family_members",
    "student_guardian_relationships",
    "academic_periods",
    "enrollments",
)

TENANT_EXPR = """
organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
"""


def tenant_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.Uuid(),
            sa.ForeignKey("institutions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    ]


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


def profile_table(name: str, code_name: str, unique_name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column(
            "person_id",
            sa.Uuid(),
            sa.ForeignKey("persons.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(code_name, sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name=f"ck_{name}_status",
        ),
        sa.UniqueConstraint("institution_id", "person_id", name=unique_name),
    )
    op.create_index(f"ix_{name}_org", name, ["organization_id"])
    op.create_index(f"ix_{name}_inst", name, ["institution_id"])
    op.create_index(f"ix_{name}_person", name, ["person_id"])


def upgrade() -> None:
    profile_table(
        "student_profiles",
        "student_code",
        "uq_student_profiles_institution_person",
    )
    op.add_column(
        "student_profiles",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    profile_table(
        "guardian_profiles",
        "guardian_code",
        "uq_guardian_profiles_institution_person",
    )
    profile_table(
        "staff_profiles",
        "staff_code",
        "uq_staff_profiles_institution_person",
    )

    op.create_table(
        "family_households",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','ARCHIVED')",
            name="ck_family_households_status",
        ),
    )
    op.create_index("ix_family_households_org", "family_households", ["organization_id"])
    op.create_index("ix_family_households_inst", "family_households", ["institution_id"])

    op.create_table(
        "family_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column(
            "family_id",
            sa.Uuid(),
            sa.ForeignKey("family_households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.Uuid(),
            sa.ForeignKey("persons.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("member_role", sa.String(20), nullable=False),
        sa.Column("relationship_label", sa.String(40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "member_role IN ('STUDENT','GUARDIAN','OTHER')",
            name="ck_family_members_role",
        ),
        sa.UniqueConstraint("family_id", "person_id", name="uq_family_members_family_person"),
    )
    op.create_index("ix_family_members_org", "family_members", ["organization_id"])
    op.create_index("ix_family_members_inst", "family_members", ["institution_id"])
    op.create_index("ix_family_members_family", "family_members", ["family_id"])
    op.create_index("ix_family_members_person", "family_members", ["person_id"])

    op.create_table(
        "student_guardian_relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column(
            "student_profile_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "guardian_profile_id",
            sa.Uuid(),
            sa.ForeignKey("guardian_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("is_legal_guardian", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_primary_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lives_with_student", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pickup_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("emergency_contact", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "student_profile_id",
            "guardian_profile_id",
            name="uq_student_guardian_pair",
        ),
    )
    op.create_index(
        "ix_student_guardian_org",
        "student_guardian_relationships",
        ["organization_id"],
    )
    op.create_index(
        "ix_student_guardian_inst",
        "student_guardian_relationships",
        ["institution_id"],
    )

    op.create_table(
        "academic_periods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED','ACTIVE','CLOSED')",
            name="ck_academic_periods_status",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_academic_periods_dates"),
        sa.UniqueConstraint(
            "institution_id",
            "code",
            name="uq_academic_periods_institution_code",
        ),
    )
    op.create_index("ix_academic_periods_org", "academic_periods", ["organization_id"])
    op.create_index("ix_academic_periods_inst", "academic_periods", ["institution_id"])

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *tenant_columns(),
        sa.Column(
            "student_profile_id",
            sa.Uuid(),
            sa.ForeignKey("student_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "academic_period_id",
            sa.Uuid(),
            sa.ForeignKey("academic_periods.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "campus_id",
            sa.Uuid(),
            sa.ForeignKey("campuses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("enrollment_number", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("enrolled_on", sa.Date(), nullable=True),
        sa.Column("withdrawn_on", sa.Date(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('PENDING','ACTIVE','WITHDRAWN','COMPLETED','CANCELLED')",
            name="ck_enrollments_status",
        ),
        sa.UniqueConstraint(
            "student_profile_id",
            "academic_period_id",
            name="uq_enrollments_student_period",
        ),
    )
    op.create_index("ix_enrollments_org", "enrollments", ["organization_id"])
    op.create_index("ix_enrollments_inst", "enrollments", ["institution_id"])
    op.create_index("ix_enrollments_student", "enrollments", ["student_profile_id"])
    op.create_index("ix_enrollments_period", "enrollments", ["academic_period_id"])
    op.create_index("ix_enrollments_campus", "enrollments", ["campus_id"])

    for table in M1_TABLES:
        enable_rls(table)


def downgrade() -> None:
    for table in reversed(M1_TABLES):
        op.drop_table(table)
