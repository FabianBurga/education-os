"""M7 hardening and pilot readiness.

Revision ID: 0008_m7
Revises: 0007_m6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_m7"
down_revision: str | None = "0007_m6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

TENANT_EXPR = """
organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
"""


def upgrade() -> None:
    op.create_table(
        "pilot_readiness_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("executed_by_user_id", UUID, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checks_total", sa.Integer(), nullable=False),
        sa.Column("checks_passed", sa.Integer(), nullable=False),
        sa.Column("checks_failed", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_pilot_readiness_runs_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["executed_by_user_id"],
            ["user_accounts.id"],
            name="fk_pilot_readiness_runs_user",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('PASS','FAIL')",
            name="ck_pilot_readiness_runs_status",
        ),
        sa.CheckConstraint(
            "checks_total >= 0 AND checks_passed >= 0 AND checks_failed >= 0",
            name="ck_pilot_readiness_runs_nonnegative",
        ),
        sa.CheckConstraint(
            "checks_passed + checks_failed = checks_total",
            name="ck_pilot_readiness_runs_consistency",
        ),
    )

    op.create_index(
        "ix_pilot_readiness_runs_organization",
        "pilot_readiness_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_pilot_readiness_runs_institution",
        "pilot_readiness_runs",
        ["institution_id"],
    )
    op.create_index(
        "ix_pilot_readiness_runs_user",
        "pilot_readiness_runs",
        ["executed_by_user_id"],
    )
    op.create_index(
        "ix_pilot_readiness_runs_executed_at",
        "pilot_readiness_runs",
        ["executed_at"],
    )

    op.execute('ALTER TABLE "pilot_readiness_runs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "pilot_readiness_runs" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY pilot_readiness_runs_tenant_isolation
        ON pilot_readiness_runs
        FOR ALL
        TO education_app
        USING ({TENANT_EXPR})
        WITH CHECK ({TENANT_EXPR})
        """
    )
    op.execute(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON "pilot_readiness_runs" TO education_app'
    )


def downgrade() -> None:
    op.drop_table("pilot_readiness_runs")
