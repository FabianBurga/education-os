"""M24-3 bounded CSV student/enrollment vertical slice.

Revision ID: 0032_m24_csv_student_enrollment
Revises: 0031_m24_integration_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032_m24_csv_student_enrollment"
down_revision: str | None = "0031_m24_integration_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"


def upgrade() -> None:
    # FILE_CSV remains a non-executable M24-2 definition for compatibility;
    # CSV_STUDENT_ENROLLMENT is the sole executable connector type.
    op.drop_constraint("ck_integration_connectors_type", "integration_connectors", type_="check")
    op.create_check_constraint(
        "ck_integration_connectors_type", "integration_connectors",
        "connector_type IN ('FILE_CSV','CSV_STUDENT_ENROLLMENT')",
    )
    op.drop_constraint("ck_integration_run_events_type", "integration_run_events", type_="check")
    op.create_check_constraint(
        "ck_integration_run_events_type", "integration_run_events",
        "event_type IN ('CREATED','VALIDATING','VALIDATED','APPLYING','COMPLETED','FAILED','CANCELLED','ITEM_APPLIED','ITEM_FAILED')",
    )
    op.create_table(
        "integration_external_student_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_connectors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_student_id", sa.String(length=120), nullable=False),
        sa.Column("student_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("student_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(external_student_id)) > 0", name="ck_integration_external_student_refs_external_id"),
        sa.UniqueConstraint("institution_id", "connector_id", "external_student_id", name="uq_integration_external_student_refs_identity"),
    )
    op.create_index(
        "ix_integration_external_student_refs_tenant", "integration_external_student_refs",
        ["organization_id", "institution_id", "connector_id", "external_student_id"],
    )
    op.execute('ALTER TABLE "integration_external_student_refs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "integration_external_student_refs" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT ON "integration_external_student_refs" TO education_app')
    op.execute(
        "CREATE POLICY integration_external_student_refs_select ON integration_external_student_refs "
        f"FOR SELECT TO education_app USING ({TENANT} AND education_os_m24_has_permission('integrations.view'))"
    )
    op.execute(
        "CREATE POLICY integration_external_student_refs_insert ON integration_external_student_refs "
        "FOR INSERT TO education_app WITH CHECK ("
        f"{TENANT} AND EXISTS (SELECT 1 FROM integration_runs r WHERE r.id=created_run_id "
        f"AND r.organization_id=organization_id AND r.institution_id=institution_id "
        f"AND r.initiated_by_user_id={USER_CTX}) AND education_os_m24_has_permission('integrations.run'))"
    )


def downgrade() -> None:
    op.drop_table("integration_external_student_refs")
    op.drop_constraint("ck_integration_run_events_type", "integration_run_events", type_="check")
    op.create_check_constraint(
        "ck_integration_run_events_type", "integration_run_events",
        "event_type IN ('CREATED','VALIDATING','VALIDATED','APPLYING','COMPLETED','FAILED','CANCELLED')",
    )
    op.drop_constraint("ck_integration_connectors_type", "integration_connectors", type_="check")
    op.create_check_constraint("ck_integration_connectors_type", "integration_connectors", "connector_type = 'FILE_CSV'")
