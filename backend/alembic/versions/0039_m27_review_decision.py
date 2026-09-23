"""M27 human review, bounded decision, and ownership ledgers.

Revision ID: 0039_m27_review_decision
Revises: 0038_m27_accountability
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039_m27_review_decision"
down_revision: str | None = "0038_m27_accountability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"
MANAGER_ROLES = ("RECTOR", "ACADEMIC_COORDINATOR")


def _permission(bind, key: str, description: str):
    value = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar_one_or_none()
    if value is None:
        value = uuid4()
        bind.execute(sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"), {"id": value, "key": key, "description": description})
    return value


def _grant(bind, permission_id, roles: tuple[str, ...]) -> None:
    for role_id in bind.execute(sa.text("SELECT id FROM roles WHERE key = ANY(CAST(:keys AS text[]))"), {"keys": list(roles)}).scalars():
        bind.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"), {"role_id": role_id, "permission_id": permission_id})


def _common_columns() -> list[sa.Column]:
    return [sa.Column("id", UUID, primary_key=True), sa.Column("organization_id", UUID, nullable=False), sa.Column("institution_id", UUID, nullable=False), sa.Column("case_id", UUID, nullable=False), sa.Column("effective_permission_context_json", postgresql.JSONB(), nullable=False), sa.Column("idempotency_key", sa.String(64), nullable=False), sa.Column("provenance_sha256", sa.String(64), nullable=False), sa.Column("canonical_event_id", UUID, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))]


def upgrade() -> None:
    bind = op.get_bind()
    permissions = (
        ("accountability.review", "Record scoped human accountability reviews."),
        ("accountability.decide", "Record scoped bounded institutional decisions."),
        ("accountability.ownership.manage", "Assign and transfer scoped accountability ownership."),
    )
    for key, description in permissions:
        _grant(bind, _permission(bind, key, description), MANAGER_ROLES)

    op.create_table(
        "accountability_reviews",
        *_common_columns(),
        sa.Column("reviewer_user_id", UUID, nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("evidence_refs_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("projection_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("policy_key", sa.String(120), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("note_reference", sa.String(240), nullable=True),
        sa.Column("next_required_step", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "case_id"], ["accountability_cases.institution_id", "accountability_cases.organization_id", "accountability_cases.id"], name="fk_accountability_reviews_case", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"], name="fk_accountability_reviews_reviewer", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_event_id"], ["outbox_events.id"], name="fk_accountability_reviews_event", ondelete="RESTRICT"),
        sa.CheckConstraint("disposition IN ('CONFIRMED','NEEDS_INFORMATION','CONTINUE_MONITORING','READY_FOR_DECISION','NO_CURRENT_CONCERN')", name="ck_accountability_reviews_disposition"),
        sa.CheckConstraint("source_version >= 1 AND projection_version >= 1", name="ck_accountability_reviews_versions"),
        sa.CheckConstraint("evidence_fingerprint_sha256 ~ '^[0-9a-f]{64}$' AND provenance_sha256 ~ '^[0-9a-f]{64}$' AND idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_reviews_hashes"),
        sa.CheckConstraint("policy_version IS NULL OR policy_version >= 1", name="ck_accountability_reviews_policy_version"),
        sa.UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_reviews_idempotency"),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_accountability_reviews_tenant_id"),
    )
    op.create_table(
        "accountability_decisions",
        *_common_columns(),
        sa.Column("decision_actor_user_id", UUID, nullable=False),
        sa.Column("review_id", UUID, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_type", sa.String(32), nullable=False),
        sa.Column("evidence_refs_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("reason_reference", sa.String(240), nullable=True),
        sa.Column("execution_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "case_id"], ["accountability_cases.institution_id", "accountability_cases.organization_id", "accountability_cases.id"], name="fk_accountability_decisions_case", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "review_id"], ["accountability_reviews.institution_id", "accountability_reviews.organization_id", "accountability_reviews.id"], name="fk_accountability_decisions_review", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decision_actor_user_id"], ["user_accounts.id"], name="fk_accountability_decisions_actor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_event_id"], ["outbox_events.id"], name="fk_accountability_decisions_event", ondelete="RESTRICT"),
        sa.CheckConstraint("decision_type IN ('NO_ACTION_REQUIRED','MONITOR','REQUEST_INFORMATION','CREATE_INTERVENTION','CONTINUE_INTERVENTION','ESCALATE','CLOSE_CASE')", name="ck_accountability_decisions_type"),
        sa.CheckConstraint("evidence_fingerprint_sha256 ~ '^[0-9a-f]{64}$' AND provenance_sha256 ~ '^[0-9a-f]{64}$' AND idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_decisions_hashes"),
        sa.CheckConstraint("policy_version IS NULL OR policy_version >= 1", name="ck_accountability_decisions_policy_version"),
        sa.UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_decisions_idempotency"),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_accountability_decisions_tenant_id"),
    )
    op.create_table(
        "accountability_ownership_events",
        *_common_columns(),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("previous_owner_user_id", UUID, nullable=True),
        sa.Column("new_owner_user_id", UUID, nullable=True),
        sa.Column("changed_by_user_id", UUID, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_reference", sa.String(240), nullable=True),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "case_id"], ["accountability_cases.institution_id", "accountability_cases.organization_id", "accountability_cases.id"], name="fk_accountability_ownership_case", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["user_accounts.id"], name="fk_accountability_ownership_actor", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_owner_user_id"], ["user_accounts.id"], name="fk_accountability_ownership_previous", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["new_owner_user_id"], ["user_accounts.id"], name="fk_accountability_ownership_new", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_event_id"], ["outbox_events.id"], name="fk_accountability_ownership_event", ondelete="RESTRICT"),
        sa.CheckConstraint("event_type IN ('ASSIGNED','TRANSFERRED','UNASSIGNED')", name="ck_accountability_ownership_type"),
        sa.CheckConstraint("provenance_sha256 ~ '^[0-9a-f]{64}$' AND idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_accountability_ownership_hashes"),
        sa.CheckConstraint("(event_type = 'UNASSIGNED' AND new_owner_user_id IS NULL) OR (event_type IN ('ASSIGNED','TRANSFERRED') AND new_owner_user_id IS NOT NULL)", name="ck_accountability_ownership_new_owner"),
        sa.UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_ownership_idempotency"),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_accountability_ownership_tenant_id"),
    )
    tables = ("accountability_reviews", "accountability_decisions", "accountability_ownership_events")
    for table in tables:
        op.create_index(f"ix_{table}_tenant", table, ["organization_id", "institution_id", "created_at"])
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'GRANT SELECT, INSERT ON "{table}" TO education_app')
        op.execute(f"""CREATE POLICY {table}_select ON {table} FOR SELECT TO education_app USING ({TENANT} AND EXISTS (SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id WHERE m.user_id={USER_CTX} AND m.institution_id={INST_CTX} AND m.status='ACTIVE' AND p.key='accountability.view'))""")
    op.execute("""CREATE POLICY accountability_reviews_insert ON accountability_reviews FOR INSERT TO education_app WITH CHECK (""" + TENANT + " AND reviewer_user_id = " + USER_CTX + " AND EXISTS (SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id WHERE m.user_id=" + USER_CTX + " AND m.institution_id=" + INST_CTX + " AND m.status='ACTIVE' AND p.key='accountability.review'))")
    op.execute("""CREATE POLICY accountability_decisions_insert ON accountability_decisions FOR INSERT TO education_app WITH CHECK (""" + TENANT + " AND decision_actor_user_id = " + USER_CTX + " AND EXISTS (SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id WHERE m.user_id=" + USER_CTX + " AND m.institution_id=" + INST_CTX + " AND m.status='ACTIVE' AND p.key='accountability.decide'))")
    op.execute("""CREATE POLICY accountability_ownership_events_insert ON accountability_ownership_events FOR INSERT TO education_app WITH CHECK (""" + TENANT + " AND changed_by_user_id = " + USER_CTX + " AND EXISTS (SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id WHERE m.user_id=" + USER_CTX + " AND m.institution_id=" + INST_CTX + " AND m.status='ACTIVE' AND p.key='accountability.ownership.manage'))")


def downgrade() -> None:
    for table in ("accountability_ownership_events", "accountability_decisions", "accountability_reviews"):
        op.drop_table(table)
    bind = op.get_bind()
    ids = bind.execute(sa.text("SELECT id FROM permissions WHERE key IN ('accountability.review','accountability.decide','accountability.ownership.manage')")).scalars().all()
    for permission_id in ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key IN ('accountability.review','accountability.decide','accountability.ownership.manage')"))
