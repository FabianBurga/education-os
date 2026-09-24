"""Add M27 accountability obligations and policy-backed SLA projection.

Revision ID: 0040_m27_obligations_sla
Revises: 0039_m27_review_decision
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0040_m27_obligations_sla"
down_revision: str | None = "0039_m27_review_decision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"


def _permission(bind: sa.Connection, key: str, description: str):
    value = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar_one_or_none()
    if value is None:
        value = uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
            {"id": value, "key": key, "description": description},
        )
    return value


def _grant(bind: sa.Connection, permission_id, roles: tuple[str, ...]) -> None:
    for role_id in bind.execute(
        sa.text("SELECT id FROM roles WHERE key = ANY(CAST(:keys AS text[]))"),
        {"keys": list(roles)},
    ).scalars():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def _has_permission(permission: str) -> str:
    return f"""EXISTS (
        SELECT 1
        FROM memberships m
        JOIN membership_roles mr ON mr.membership_id = m.id
        JOIN role_permissions rp ON rp.role_id = mr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE m.user_id = {USER_CTX}
          AND m.institution_id = {INST_CTX}
          AND m.status = 'ACTIVE'
          AND p.key = '{permission}'
    )"""


def upgrade() -> None:
    bind = op.get_bind()
    roles = ("RECTOR", "ACADEMIC_COORDINATOR")
    permissions = {
        "accountability.obligation.create": "Materialize scoped accountability obligations.",
        "accountability.obligation.complete": "Complete scoped accountability obligations.",
        "accountability.obligation.waive": "Waive scoped accountability obligations.",
        "accountability.obligation.ownership.manage": "Transfer scoped obligation ownership.",
    }
    for key, description in permissions.items():
        _grant(bind, _permission(bind, key, description), roles)

    op.create_table(
        "accountability_obligations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("origin_type", sa.String(24), nullable=False),
        sa.Column("origin_id", UUID, nullable=False),
        sa.Column("obligation_type", sa.String(32), nullable=False),
        sa.Column("next_required_step", sa.String(64), nullable=False),
        sa.Column("identity_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("identity_key_sha256", sa.String(64), nullable=False),
        sa.Column("owner_user_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_status", sa.String(24), nullable=False),
        sa.Column("sla_policy_key", sa.String(120), nullable=True),
        sa.Column("sla_policy_version", sa.Integer(), nullable=True),
        sa.Column("sla_rule_code", sa.String(160), nullable=True),
        sa.Column("sla_resolution_sha256", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", UUID, nullable=True),
        sa.Column("completion_evidence_type", sa.String(32), nullable=True),
        sa.Column("completion_evidence_id", UUID, nullable=True),
        sa.Column("completion_evidence_fingerprint_sha256", sa.String(64), nullable=True),
        sa.Column("completion_idempotency_key", sa.String(64), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_by_user_id", UUID, nullable=True),
        sa.Column("waiver_reason_code", sa.String(64), nullable=True),
        sa.Column("waiver_evidence_id", UUID, nullable=True),
        sa.Column("waiver_idempotency_key", sa.String(64), nullable=True),
        sa.Column("owner_transfer_idempotency_key", sa.String(64), nullable=True),
        sa.Column("predecessor_obligation_id", UUID, nullable=True),
        sa.Column("projection_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provenance_sha256", sa.String(64), nullable=False),
        sa.Column("creation_idempotency_key", sa.String(64), nullable=False),
        sa.Column("canonical_event_id", UUID, nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id", "case_id"],
            ["accountability_cases.institution_id", "accountability_cases.organization_id", "accountability_cases.id"],
            name="fk_accountability_obligations_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"], name="fk_accountability_obligations_owner", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["user_accounts.id"], name="fk_accountability_obligations_completed_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["waived_by_user_id"], ["user_accounts.id"], name="fk_accountability_obligations_waived_by", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"], name="fk_accountability_obligations_created_by", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["predecessor_obligation_id"], ["accountability_obligations.id"], name="fk_accountability_obligations_predecessor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_event_id"], ["outbox_events.id"], name="fk_accountability_obligations_event", ondelete="RESTRICT"),
        sa.CheckConstraint("origin_type IN ('DECISION','REVIEW','CASE')", name="ck_accountability_obligations_origin"),
        sa.CheckConstraint("obligation_type IN ('INFORMATION_REQUIRED','REVIEW_REQUIRED','FOLLOW_UP_REQUIRED')", name="ck_accountability_obligations_type"),
        sa.CheckConstraint("identity_version >= 1 AND projection_version >= 1 AND source_version >= 1", name="ck_accountability_obligations_versions"),
        sa.CheckConstraint("identity_key_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_identity_sha"),
        sa.CheckConstraint("sla_status IN ('RESOLVED','NOT_EVALUABLE')", name="ck_accountability_obligations_sla_status"),
        sa.CheckConstraint("sla_policy_version IS NULL OR sla_policy_version >= 1", name="ck_accountability_obligations_policy_version"),
        sa.CheckConstraint("sla_resolution_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_sla_resolution_sha"),
        sa.CheckConstraint("lifecycle IN ('OPEN','IN_PROGRESS','COMPLETED','WAIVED','EXPIRED','CANCELLED')", name="ck_accountability_obligations_lifecycle"),
        sa.CheckConstraint("completion_evidence_type IS NULL OR completion_evidence_type IN ('M21_FOLLOW_UP','M21_ACTION','M27_HUMAN_REVIEW','M27_INFORMATION')", name="ck_accountability_obligations_evidence_type"),
        sa.CheckConstraint("completion_idempotency_key IS NULL OR completion_idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_completion_idempotency_sha"),
        sa.CheckConstraint("waiver_idempotency_key IS NULL OR waiver_idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_waiver_idempotency_sha"),
        sa.CheckConstraint("owner_transfer_idempotency_key IS NULL OR owner_transfer_idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_owner_transfer_idempotency_sha"),
        sa.CheckConstraint("provenance_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_provenance_sha"),
        sa.CheckConstraint("creation_idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_obligations_creation_idempotency_sha"),
        sa.UniqueConstraint("institution_id", "identity_version", "identity_key_sha256", name="uq_accountability_obligations_identity"),
        sa.UniqueConstraint("institution_id", "creation_idempotency_key", name="uq_accountability_obligations_creation_idempotency"),
        sa.UniqueConstraint("institution_id", "completion_idempotency_key", name="uq_accountability_obligations_completion_idempotency"),
        sa.UniqueConstraint("institution_id", "waiver_idempotency_key", name="uq_accountability_obligations_waiver_idempotency"),
        sa.UniqueConstraint("institution_id", "owner_transfer_idempotency_key", name="uq_accountability_obligations_owner_transfer_idempotency"),
    )
    op.create_index("ix_accountability_obligations_tenant_lifecycle", "accountability_obligations", ["organization_id", "institution_id", "lifecycle", "due_at"])
    op.create_index("ix_accountability_obligations_case_lifecycle", "accountability_obligations", ["institution_id", "case_id", "lifecycle"])
    op.execute('ALTER TABLE "accountability_obligations" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "accountability_obligations" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT, UPDATE ON "accountability_obligations" TO education_app')
    op.execute(f"""
        CREATE POLICY accountability_obligations_select ON accountability_obligations
        FOR SELECT TO education_app
        USING ({TENANT} AND {_has_permission('accountability.view')})
    """)
    op.execute(f"""
        CREATE POLICY accountability_obligations_insert ON accountability_obligations
        FOR INSERT TO education_app
        WITH CHECK ({TENANT} AND {_has_permission('accountability.obligation.create')})
    """)
    operation_permissions = " OR ".join(
        _has_permission(key)
        for key in (
            "accountability.obligation.complete",
            "accountability.obligation.waive",
            "accountability.obligation.ownership.manage",
        )
    )
    op.execute(f"""
        CREATE POLICY accountability_obligations_update ON accountability_obligations
        FOR UPDATE TO education_app
        USING ({TENANT} AND ({operation_permissions}))
        WITH CHECK ({TENANT} AND ({operation_permissions}))
    """)


def downgrade() -> None:
    op.drop_index("ix_accountability_obligations_case_lifecycle", table_name="accountability_obligations")
    op.drop_index("ix_accountability_obligations_tenant_lifecycle", table_name="accountability_obligations")
    op.drop_table("accountability_obligations")
    bind = op.get_bind()
    keys = (
        "accountability.obligation.create",
        "accountability.obligation.complete",
        "accountability.obligation.waive",
        "accountability.obligation.ownership.manage",
    )
    permission_ids = bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"),
        {"keys": list(keys)},
    ).scalars().all()
    for permission_id in permission_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key = ANY(CAST(:keys AS text[]))"), {"keys": list(keys)})
