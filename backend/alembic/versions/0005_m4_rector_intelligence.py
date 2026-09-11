"""M4 rector intelligence.

Revision ID: 0005_m4
Revises: 0004_m3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_m4"
down_revision: str | None = "0004_m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

TENANT_EXPR = """
organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
"""


def upgrade() -> None:
    op.create_table(
        "intelligence_signals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("section_id", UUID, nullable=True),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("signal_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("metric_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("threshold_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.String(1000), nullable=True),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_intelligence_signals_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_intelligence_signals_period_inst",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "institution_id"],
            ["sections.id", "sections.institution_id"],
            name="fk_intelligence_signals_section_inst",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_intelligence_signals_student_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "signal_type IN ('ATTENDANCE_RISK','REPEATED_LATE','ACADEMIC_RISK','MISSING_WORK')",
            name="ck_intelligence_signals_type",
        ),
        sa.CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH')",
            name="ck_intelligence_signals_severity",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','RESOLVED','CLOSED')",
            name="ck_intelligence_signals_status",
        ),
        sa.UniqueConstraint(
            "student_profile_id",
            "academic_period_id",
            "signal_type",
            "status",
            name="uq_intelligence_signal_student_period_type_status",
        ),
    )

    op.create_index(
        "ix_intelligence_signals_organization",
        "intelligence_signals",
        ["organization_id"],
    )
    op.create_index(
        "ix_intelligence_signals_institution",
        "intelligence_signals",
        ["institution_id"],
    )
    op.create_index(
        "ix_intelligence_signals_student",
        "intelligence_signals",
        ["student_profile_id"],
    )
    op.create_index(
        "ix_intelligence_signals_status",
        "intelligence_signals",
        ["status"],
    )
    op.create_index(
        "ix_intelligence_signals_section",
        "intelligence_signals",
        ["section_id"],
    )

    op.execute('ALTER TABLE "intelligence_signals" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "intelligence_signals" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY intelligence_signals_tenant_isolation
        ON intelligence_signals
        FOR ALL
        TO education_app
        USING ({TENANT_EXPR})
        WITH CHECK ({TENANT_EXPR})
        """
    )
    op.execute(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON "intelligence_signals" TO education_app'
    )


def downgrade() -> None:
    op.drop_table("intelligence_signals")
