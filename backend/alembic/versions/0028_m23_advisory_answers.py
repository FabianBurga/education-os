"""M23 provider gateway advisory answer persistence.

Revision ID: 0028_m23_advisory_answers
Revises: 0027_m23_copilot_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028_m23_advisory_answers"
down_revision: str | None = "0027_m23_copilot_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"


def upgrade() -> None:
    op.create_table(
        "copilot_advisory_outputs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column(
            "citations_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence_assessment",
            sa.String(20),
            nullable=False,
        ),
        sa.Column(
            "limitations_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("provider_response_id", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_copilot_advisory_outputs_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["copilot_runs.id"],
            name="fk_copilot_advisory_outputs_run",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('ANSWER','INSUFFICIENT_EVIDENCE','REFUSED')",
            name="ck_copilot_advisory_outputs_status",
        ),
        sa.CheckConstraint(
            "evidence_assessment IN ('SUFFICIENT','LIMITED','INSUFFICIENT')",
            name="ck_copilot_advisory_outputs_assessment",
        ),
        sa.CheckConstraint(
            "length(response_sha256) = 64",
            name="ck_copilot_advisory_outputs_sha",
        ),
        sa.UniqueConstraint(
            "run_id",
            name="uq_copilot_advisory_output_run",
        ),
    )
    op.create_index(
        "ix_copilot_advisory_outputs_organization",
        "copilot_advisory_outputs",
        ["organization_id"],
    )
    op.create_index(
        "ix_copilot_advisory_outputs_institution",
        "copilot_advisory_outputs",
        ["institution_id"],
    )
    op.create_index(
        "ix_copilot_advisory_outputs_run",
        "copilot_advisory_outputs",
        ["run_id"],
    )
    op.create_index(
        "ix_copilot_advisory_outputs_created",
        "copilot_advisory_outputs",
        ["institution_id", "created_at"],
    )

    op.execute(
        'ALTER TABLE "copilot_advisory_outputs" ENABLE ROW LEVEL SECURITY'
    )
    op.execute(
        'ALTER TABLE "copilot_advisory_outputs" FORCE ROW LEVEL SECURITY'
    )
    op.execute(
        'GRANT SELECT, INSERT ON "copilot_advisory_outputs" TO education_app'
    )

    select_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        "AND EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        "AND education_os_copilot_run_visible(cr.actor_user_id)"
        ")"
    )
    insert_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        "AND EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        f"AND cr.actor_user_id = {USER_CTX}"
        ")"
    )

    op.execute(
        'CREATE POLICY copilot_advisory_outputs_select '
        'ON "copilot_advisory_outputs" '
        f"FOR SELECT TO education_app USING ({select_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_advisory_outputs_insert '
        'ON "copilot_advisory_outputs" '
        f"FOR INSERT TO education_app WITH CHECK ({insert_gate})"
    )


def downgrade() -> None:
    op.drop_table("copilot_advisory_outputs")
