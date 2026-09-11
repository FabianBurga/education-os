"""M5 automation engine.

Revision ID: 0006_m5
Revises: 0005_m4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_m5"
down_revision: str | None = "0005_m4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

M5_TABLES = (
    "automation_rules",
    "automation_cases",
    "automation_tasks",
    "automation_timeline_events",
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
    op.create_unique_constraint(
        "uq_intelligence_signals_id_inst",
        "intelligence_signals",
        ["id", "institution_id"],
    )

    op.create_table(
        "automation_rules",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("signal_type", sa.String(40), nullable=False),
        sa.Column("minimum_severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("assignee_role_code", sa.String(60), nullable=False),
        sa.Column("task_title", sa.String(200), nullable=False),
        sa.Column("due_in_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("escalate_after_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_automation_rules_tenant"),
        sa.CheckConstraint(
            "signal_type IN ('ATTENDANCE_RISK','REPEATED_LATE','ACADEMIC_RISK','MISSING_WORK')",
            name="ck_automation_rules_signal_type",
        ),
        sa.CheckConstraint(
            "minimum_severity IN ('LOW','MEDIUM','HIGH')",
            name="ck_automation_rules_min_severity",
        ),
        sa.CheckConstraint("due_in_hours > 0", name="ck_automation_rules_due"),
        sa.CheckConstraint(
            "escalate_after_hours > 0",
            name="ck_automation_rules_escalate",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "code",
            name="uq_automation_rules_inst_code",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_automation_rules_id_inst",
        ),
    )

    op.create_table(
        "automation_cases",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("intelligence_signal_id", UUID, nullable=False),
        sa.Column("automation_rule_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("section_id", UUID, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_note", sa.String(1000), nullable=True),
        tenant_constraint("fk_automation_cases_tenant"),
        sa.ForeignKeyConstraint(
            ["intelligence_signal_id", "institution_id"],
            ["intelligence_signals.id", "intelligence_signals.institution_id"],
            name="fk_automation_cases_signal_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["automation_rule_id", "institution_id"],
            ["automation_rules.id", "automation_rules.institution_id"],
            name="fk_automation_cases_rule_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_automation_cases_student_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "institution_id"],
            ["sections.id", "sections.institution_id"],
            name="fk_automation_cases_section_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','CLOSED','CANCELLED')",
            name="ck_automation_cases_status",
        ),
        sa.UniqueConstraint(
            "intelligence_signal_id",
            "automation_rule_id",
            name="uq_automation_cases_signal_rule",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_automation_cases_id_inst",
        ),
    )

    op.create_table(
        "automation_tasks",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("automation_case_id", UUID, nullable=False),
        sa.Column("assigned_role_code", sa.String(60), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False, server_default="REVIEW"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalate_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_note", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_automation_tasks_tenant"),
        sa.ForeignKeyConstraint(
            ["automation_case_id", "institution_id"],
            ["automation_cases.id", "automation_cases.institution_id"],
            name="fk_automation_tasks_case_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "task_type IN ('REVIEW','FOLLOW_UP','COMMUNICATION','OTHER')",
            name="ck_automation_tasks_type",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','ESCALATED','COMPLETED','CANCELLED')",
            name="ck_automation_tasks_status",
        ),
        sa.CheckConstraint(
            "escalate_at >= due_at",
            name="ck_automation_tasks_escalation_after_due",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_automation_tasks_id_inst",
        ),
    )

    op.create_table(
        "automation_timeline_events",
        sa.Column("id", UUID, primary_key=True),
        *tenant_columns(),
        sa.Column("automation_case_id", UUID, nullable=False),
        sa.Column("automation_task_id", UUID, nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        tenant_constraint("fk_automation_timeline_tenant"),
        sa.ForeignKeyConstraint(
            ["automation_case_id", "institution_id"],
            ["automation_cases.id", "automation_cases.institution_id"],
            name="fk_automation_timeline_case_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["automation_task_id", "institution_id"],
            ["automation_tasks.id", "automation_tasks.institution_id"],
            name="fk_automation_timeline_task_inst",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "event_type IN ('CASE_OPENED','TASK_CREATED','TASK_ACKNOWLEDGED','TASK_ESCALATED','TASK_COMPLETED','CASE_CLOSED')",
            name="ck_automation_timeline_type",
        ),
    )

    for table in M5_TABLES:
        op.create_index(f"ix_{table}_organization", table, ["organization_id"])
        op.create_index(f"ix_{table}_institution", table, ["institution_id"])
        enable_rls(table)


def downgrade() -> None:
    for table in reversed(M5_TABLES):
        op.drop_table(table)

    op.drop_constraint(
        "uq_intelligence_signals_id_inst",
        "intelligence_signals",
        type_="unique",
    )
