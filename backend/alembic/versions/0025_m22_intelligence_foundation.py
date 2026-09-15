"""M22 secure institutional intelligence analytical foundation.

Revision ID: 0025_m22_intelligence_foundation
Revises: 0024_m21_projection_boundary
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_m22_intelligence_foundation"
down_revision: str | None = "0024_m21_projection_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

M22_TABLES = (
    "student_intelligence_snapshots",
    "cohort_intelligence_daily",
    "institution_intelligence_daily",
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


def _enable_tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO education_app'
    )
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_isolation
        ON "{table}"
        FOR ALL
        TO education_app
        USING ({TENANT})
        WITH CHECK ({TENANT})
        """
    )


def _policy_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "rule_set_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "projection_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "policy_source",
            sa.String(30),
            nullable=False,
            server_default="BUILTIN_DEFAULT",
        ),
        sa.Column(
            "policy_key",
            sa.String(120),
            nullable=False,
            server_default="institutional_intelligence",
        ),
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("control_revision", sa.BigInteger(), nullable=True),
    ]


def _policy_constraints(prefix: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            "rule_set_version >= 1",
            name=f"ck_{prefix}_rule_set_version",
        ),
        sa.CheckConstraint(
            "projection_version >= 1",
            name=f"ck_{prefix}_projection_version",
        ),
        sa.CheckConstraint(
            "policy_version >= 1",
            name=f"ck_{prefix}_policy_version",
        ),
        sa.CheckConstraint(
            "policy_source IN ('BUILTIN_DEFAULT','CONTROL_PLANE')",
            name=f"ck_{prefix}_policy_source",
        ),
        sa.CheckConstraint(
            "length(trim(policy_key)) > 0",
            name=f"ck_{prefix}_policy_key",
        ),
        sa.CheckConstraint(
            "("
            "policy_source = 'BUILTIN_DEFAULT' "
            "AND control_revision IS NULL"
            ") OR ("
            "policy_source = 'CONTROL_PLANE' "
            "AND control_revision IS NOT NULL "
            "AND control_revision > 0"
            ")",
            name=f"ck_{prefix}_policy_provenance",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "student_intelligence_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("overall_priority", sa.String(20), nullable=False),
        sa.Column("attendance_priority", sa.String(20), nullable=False),
        sa.Column("academic_priority", sa.String(20), nullable=False),
        sa.Column("intervention_priority", sa.String(20), nullable=False),
        sa.Column(
            "evidence_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        *_policy_columns(),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_student_intelligence_snapshots_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_student_intelligence_snapshots_student_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_student_intelligence_snapshots_period_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "overall_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_overall_priority",
        ),
        sa.CheckConstraint(
            "attendance_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_attendance_priority",
        ),
        sa.CheckConstraint(
            "academic_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_academic_priority",
        ),
        sa.CheckConstraint(
            "intervention_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_intervention_priority",
        ),
        sa.CheckConstraint(
            "evidence_count >= 0",
            name="ck_student_intelligence_snapshots_evidence_count",
        ),
        sa.CheckConstraint(
            "window_end IS NULL OR window_start IS NULL OR window_end >= window_start",
            name="ck_student_intelligence_snapshots_window",
        ),
        *_policy_constraints("student_intelligence_snapshots"),
        sa.UniqueConstraint(
            "institution_id",
            "student_profile_id",
            "snapshot_date",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            name="uq_student_intelligence_snapshots_identity",
        ),
    )
    _tenant_indexes("student_intelligence_snapshots")
    op.create_index(
        "ix_student_intelligence_snapshots_student",
        "student_intelligence_snapshots",
        ["student_profile_id"],
    )
    op.create_index(
        "ix_student_intelligence_snapshots_period",
        "student_intelligence_snapshots",
        ["academic_period_id"],
    )
    op.create_index(
        "ix_student_intelligence_snapshots_date",
        "student_intelligence_snapshots",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_student_intelligence_snapshots_priority_queue",
        "student_intelligence_snapshots",
        ["institution_id", "snapshot_date", "overall_priority"],
    )
    op.create_index(
        "ix_student_intelligence_snapshots_student_date",
        "student_intelligence_snapshots",
        ["institution_id", "student_profile_id", "snapshot_date"],
    )

    op.create_table(
        "cohort_intelligence_daily",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("cohort_type", sa.String(30), nullable=False),
        sa.Column("cohort_ref_id", UUID, nullable=True),
        sa.Column("student_count", sa.Integer(), nullable=False),
        sa.Column("high_priority_count", sa.Integer(), nullable=True),
        sa.Column("medium_priority_count", sa.Integer(), nullable=True),
        sa.Column("attendance_risk_count", sa.Integer(), nullable=True),
        sa.Column("academic_risk_count", sa.Integer(), nullable=True),
        sa.Column("active_intervention_count", sa.Integer(), nullable=True),
        sa.Column("overdue_followup_count", sa.Integer(), nullable=True),
        sa.Column(
            "suppressed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        *_policy_columns(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_cohort_intelligence_daily_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_cohort_intelligence_daily_period_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "cohort_type IN "
            "('INSTITUTION','ACADEMIC_LEVEL','GRADE','SECTION','COURSE')",
            name="ck_cohort_intelligence_daily_type",
        ),
        sa.CheckConstraint(
            "("
            "cohort_type = 'INSTITUTION' AND cohort_ref_id IS NULL"
            ") OR ("
            "cohort_type <> 'INSTITUTION' AND cohort_ref_id IS NOT NULL"
            ")",
            name="ck_cohort_intelligence_daily_identity",
        ),
        sa.CheckConstraint(
            "student_count >= 0",
            name="ck_cohort_intelligence_daily_student_count",
        ),
        sa.CheckConstraint(
            "("
            "suppressed = true "
            "AND high_priority_count IS NULL "
            "AND medium_priority_count IS NULL "
            "AND attendance_risk_count IS NULL "
            "AND academic_risk_count IS NULL "
            "AND active_intervention_count IS NULL "
            "AND overdue_followup_count IS NULL"
            ") OR ("
            "suppressed = false "
            "AND high_priority_count IS NOT NULL "
            "AND medium_priority_count IS NOT NULL "
            "AND attendance_risk_count IS NOT NULL "
            "AND academic_risk_count IS NOT NULL "
            "AND active_intervention_count IS NOT NULL "
            "AND overdue_followup_count IS NOT NULL"
            ")",
            name="ck_cohort_intelligence_daily_suppression",
        ),
        sa.CheckConstraint(
            "suppressed = true OR ("
            "high_priority_count >= 0 "
            "AND medium_priority_count >= 0 "
            "AND attendance_risk_count >= 0 "
            "AND academic_risk_count >= 0 "
            "AND active_intervention_count >= 0 "
            "AND overdue_followup_count >= 0 "
            "AND high_priority_count <= student_count "
            "AND medium_priority_count <= student_count "
            "AND attendance_risk_count <= student_count "
            "AND academic_risk_count <= student_count"
            ")",
            name="ck_cohort_intelligence_daily_counts",
        ),
        *_policy_constraints("cohort_intelligence_daily"),
    )
    _tenant_indexes("cohort_intelligence_daily")
    op.create_index(
        "ix_cohort_intelligence_daily_period",
        "cohort_intelligence_daily",
        ["academic_period_id"],
    )
    op.create_index(
        "ix_cohort_intelligence_daily_date",
        "cohort_intelligence_daily",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_cohort_intelligence_daily_type_date",
        "cohort_intelligence_daily",
        ["institution_id", "snapshot_date", "cohort_type"],
    )
    op.create_index(
        "ix_cohort_intelligence_daily_ref_date",
        "cohort_intelligence_daily",
        ["institution_id", "cohort_type", "cohort_ref_id", "snapshot_date"],
    )
    op.create_index(
        "uq_cohort_intelligence_daily_identity_ref",
        "cohort_intelligence_daily",
        [
            "institution_id",
            "snapshot_date",
            "cohort_type",
            "cohort_ref_id",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
        ],
        unique=True,
        postgresql_where=sa.text("cohort_ref_id IS NOT NULL"),
    )
    op.create_index(
        "uq_cohort_intelligence_daily_identity_institution",
        "cohort_intelligence_daily",
        [
            "institution_id",
            "snapshot_date",
            "cohort_type",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
        ],
        unique=True,
        postgresql_where=sa.text(
            "cohort_type = 'INSTITUTION' AND cohort_ref_id IS NULL"
        ),
    )

    op.create_table(
        "institution_intelligence_daily",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("in_scope_student_count", sa.Integer(), nullable=False),
        sa.Column("high_priority_count", sa.Integer(), nullable=False),
        sa.Column("medium_priority_count", sa.Integer(), nullable=False),
        sa.Column("active_intervention_count", sa.Integer(), nullable=False),
        sa.Column(
            "interventions_without_action_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("overdue_followup_count", sa.Integer(), nullable=False),
        sa.Column("positive_outcome_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_outcome_count", sa.Integer(), nullable=False),
        *_policy_columns(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_institution_intelligence_daily_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_institution_intelligence_daily_period_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "in_scope_student_count >= 0 "
            "AND high_priority_count >= 0 "
            "AND medium_priority_count >= 0 "
            "AND active_intervention_count >= 0 "
            "AND interventions_without_action_count >= 0 "
            "AND overdue_followup_count >= 0 "
            "AND positive_outcome_count >= 0 "
            "AND unresolved_outcome_count >= 0",
            name="ck_institution_intelligence_daily_nonnegative",
        ),
        sa.CheckConstraint(
            "high_priority_count <= in_scope_student_count "
            "AND medium_priority_count <= in_scope_student_count",
            name="ck_institution_intelligence_daily_student_bounds",
        ),
        *_policy_constraints("institution_intelligence_daily"),
        sa.UniqueConstraint(
            "institution_id",
            "snapshot_date",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            name="uq_institution_intelligence_daily_identity",
        ),
    )
    _tenant_indexes("institution_intelligence_daily")
    op.create_index(
        "ix_institution_intelligence_daily_period",
        "institution_intelligence_daily",
        ["academic_period_id"],
    )
    op.create_index(
        "ix_institution_intelligence_daily_date",
        "institution_intelligence_daily",
        ["snapshot_date"],
    )
    op.create_index(
        "ix_institution_intelligence_daily_inst_date",
        "institution_intelligence_daily",
        ["institution_id", "snapshot_date"],
    )

    for table in M22_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    op.drop_table("cohort_intelligence_daily")
    op.drop_table("institution_intelligence_daily")
    op.drop_table("student_intelligence_snapshots")
