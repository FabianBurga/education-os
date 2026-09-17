"""M25 append-only Agentic Control Plane foundation.

Revision ID: 0033_m25_agentic_control_plane
Revises: 0032_m24_csv_student_enrollment
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033_m25_agentic_control_plane"
down_revision: str | None = "0032_m24_csv_student_enrollment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"
TABLES = (
    "agent_definitions", "agent_policy_versions", "agent_runs", "agent_run_steps",
    "agent_tool_calls", "agent_evidence_refs", "agent_run_events",
)
PERMISSIONS = (
    ("agents.view", "View tenant-scoped governed agent definitions and runs."),
    ("agents.use", "Execute tenant-scoped governed read-only agents."),
    ("agents.audit.read", "Read detailed tenant-scoped governed agent audit records."),
)


def _permission_id(bind, key: str, description: str):
    value = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar_one_or_none()
    if value is None:
        value = uuid4()
        bind.execute(sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
                     {"id": value, "key": key, "description": description})
    return value


def _grant(bind, permission_id, role_keys: tuple[str, ...]) -> None:
    for role_id in bind.execute(sa.text("SELECT id FROM roles WHERE key = ANY(CAST(:keys AS text[]))"), {"keys": list(role_keys)}).scalars():
        bind.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"),
                     {"role_id": role_id, "permission_id": permission_id})


def _tenant_columns() -> list[sa.Column]:
    return [sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "agent_definitions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("agent_key", sa.String(120), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("capability_keys_json", postgresql.JSONB(), nullable=False),
        sa.Column("tool_keys_json", postgresql.JSONB(), nullable=False), sa.Column("max_autonomy_level", sa.String(8), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False), sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("agent_key = 'integration_run_advisor'", name="ck_agent_definitions_key"),
        sa.CheckConstraint("version >= 1", name="ck_agent_definitions_version"),
        sa.CheckConstraint("status IN ('ENABLED','DISABLED')", name="ck_agent_definitions_status"),
        sa.CheckConstraint("max_autonomy_level IN ('L0','L1','L2','L3','L4','L5')", name="ck_agent_definitions_autonomy"),
        sa.CheckConstraint("jsonb_typeof(capability_keys_json) = 'array'", name="ck_agent_definitions_capabilities"),
        sa.CheckConstraint("jsonb_typeof(tool_keys_json) = 'array'", name="ck_agent_definitions_tools"),
        sa.CheckConstraint("jsonb_typeof(config_json) = 'object'", name="ck_agent_definitions_config"),
        sa.UniqueConstraint("institution_id", "agent_key", "version", name="uq_agent_definitions_version"),
    )
    op.create_table(
        "agent_policy_versions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("policy_key", sa.String(120), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("max_autonomy_level", sa.String(8), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False), sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("provider_policy", sa.String(40), nullable=False), sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_key = 'integration_run_advisor'", name="ck_agent_policy_versions_key"),
        sa.CheckConstraint("version >= 1", name="ck_agent_policy_versions_version"),
        sa.CheckConstraint("status IN ('ENABLED','DISABLED')", name="ck_agent_policy_versions_status"),
        sa.CheckConstraint("max_autonomy_level = 'L0'", name="ck_agent_policy_versions_autonomy"),
        sa.CheckConstraint("max_steps BETWEEN 1 AND 16", name="ck_agent_policy_versions_steps"),
        sa.CheckConstraint("max_tool_calls BETWEEN 1 AND 4", name="ck_agent_policy_versions_calls"),
        sa.CheckConstraint("provider_policy = 'DETERMINISTIC_ONLY'", name="ck_agent_policy_versions_provider"),
        sa.CheckConstraint("jsonb_typeof(config_json) = 'object'", name="ck_agent_policy_versions_config"),
        sa.UniqueConstraint("institution_id", "policy_key", "version", name="uq_agent_policy_versions_version"),
    )
    op.create_table(
        "agent_runs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("agent_key", sa.String(120), nullable=False),
        sa.Column("agent_definition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agent_definition_version", sa.Integer(), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_policy_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False), sa.Column("request_type", sa.String(80), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False), sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("agent_key = 'integration_run_advisor'", name="ck_agent_runs_key"),
        sa.CheckConstraint("request_type = 'M24_INTEGRATION_RUN_INSPECT'", name="ck_agent_runs_request_type"),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_runs_request_sha"),
        sa.UniqueConstraint("institution_id", "agent_key", "request_sha256", name="uq_agent_runs_request"),
    )
    for table, extra in (
        ("agent_run_steps", [sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("step_type", sa.String(40), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("summary_json", postgresql.JSONB(), nullable=False)]),
        ("agent_tool_calls", [sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("tool_key", sa.String(160), nullable=False), sa.Column("schema_version", sa.String(40), nullable=False), sa.Column("input_sha256", sa.String(64), nullable=False), sa.Column("output_sha256", sa.String(64), nullable=False), sa.Column("verification_status", sa.String(20), nullable=False), sa.Column("safe_summary_json", postgresql.JSONB(), nullable=False)]),
        ("agent_evidence_refs", [sa.Column("reference_key", sa.String(220), nullable=False), sa.Column("source_module", sa.String(80), nullable=False), sa.Column("source_entity_type", sa.String(120), nullable=False), sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("provenance_sha256", sa.String(64), nullable=False)]),
        ("agent_run_events", [sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("event_type", sa.String(30), nullable=False), sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)), sa.Column("metadata_json", postgresql.JSONB(), nullable=False)]),
    ):
        constraints = [sa.CheckConstraint("sequence >= 1", name=f"ck_{table}_sequence")] if table != "agent_evidence_refs" else []
        if table == "agent_run_steps":
            constraints += [sa.CheckConstraint("step_type IN ('PLANNER','POLICY','EXECUTOR','VERIFIER')", name="ck_agent_run_steps_type"), sa.CheckConstraint("jsonb_typeof(summary_json) = 'object'", name="ck_agent_run_steps_summary")]
        if table == "agent_tool_calls":
            constraints += [sa.CheckConstraint("tool_key = 'm24.integration_run.inspect'", name="ck_agent_tool_calls_key"), sa.CheckConstraint("verification_status IN ('VERIFIED','FAILED')", name="ck_agent_tool_calls_verification"), sa.CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$' AND output_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_tool_calls_hashes"), sa.CheckConstraint("jsonb_typeof(safe_summary_json) = 'object'", name="ck_agent_tool_calls_summary")]
        if table == "agent_evidence_refs":
            constraints += [sa.CheckConstraint("source_module = 'integrations'", name="ck_agent_evidence_refs_source"), sa.CheckConstraint("provenance_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_evidence_refs_sha")]
        if table == "agent_run_events":
            constraints += [sa.CheckConstraint("event_type IN ('CREATED','POLICY_ALLOWED','COMPLETED','FAILED')", name="ck_agent_run_events_type"), sa.CheckConstraint("jsonb_typeof(metadata_json) = 'object'", name="ck_agent_run_events_metadata")]
        unique = ("run_id", "reference_key") if table == "agent_evidence_refs" else ("run_id", "sequence")
        op.create_table(table, sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
                        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=False),
                        *extra, sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), *constraints,
                        sa.UniqueConstraint(*unique, name=f"uq_{table}_{'reference' if table == 'agent_evidence_refs' else 'sequence'}"))

    for table in TABLES:
        op.create_index(f"ix_{table}_tenant", table, ["organization_id", "institution_id", "created_at"])

    bind = op.get_bind()
    for org_id, institution_id in bind.execute(sa.text("SELECT organization_id, id FROM institutions")).all():
        bind.execute(sa.text("""
            INSERT INTO agent_definitions (id, organization_id, institution_id, agent_key, version, status, capability_keys_json, tool_keys_json, max_autonomy_level, config_json, created_by_user_id, created_at)
            VALUES (:id, :org, :inst, 'integration_run_advisor', 1, 'ENABLED', CAST(:capabilities AS jsonb), CAST(:tools AS jsonb), 'L0', '{}'::jsonb, NULL, NOW())
        """), {"id": uuid4(), "org": org_id, "inst": institution_id, "capabilities": '["integration.run.inspect"]', "tools": '["m24.integration_run.inspect"]'})
        bind.execute(sa.text("""
            INSERT INTO agent_policy_versions (id, organization_id, institution_id, policy_key, version, status, max_autonomy_level, max_steps, max_tool_calls, provider_policy, config_json, created_by_user_id, created_at)
            VALUES (:id, :org, :inst, 'integration_run_advisor', 1, 'ENABLED', 'L0', 4, 1, 'DETERMINISTIC_ONLY', '{}'::jsonb, NULL, NOW())
        """), {"id": uuid4(), "org": org_id, "inst": institution_id})

    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'GRANT SELECT, INSERT ON "{table}" TO education_app')
    op.execute("""
        CREATE FUNCTION education_os_m25_has_permission(required_permission text)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT EXISTS (
            SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
              AND m.institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
              AND m.status='ACTIVE' AND p.key=required_permission)
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION education_os_m25_has_permission(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION education_os_m25_has_permission(text) TO education_app")
    for table in TABLES:
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT TO education_app USING ({TENANT} AND education_os_m25_has_permission('agents.view'))")
    op.execute(f"CREATE POLICY agent_runs_insert ON agent_runs FOR INSERT TO education_app WITH CHECK ({TENANT} AND actor_user_id = {USER_CTX} AND education_os_m25_has_permission('agents.use'))")
    for table in ("agent_run_steps", "agent_tool_calls", "agent_evidence_refs", "agent_run_events"):
        op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT TO education_app WITH CHECK ({TENANT} AND EXISTS (SELECT 1 FROM agent_runs r WHERE r.id=run_id AND r.organization_id=organization_id AND r.institution_id=institution_id AND r.actor_user_id={USER_CTX}) AND education_os_m25_has_permission('agents.use'))")

    ids = {key: _permission_id(bind, key, description) for key, description in PERMISSIONS}
    _grant(bind, ids["agents.view"], ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR"))
    _grant(bind, ids["agents.use"], ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR"))
    _grant(bind, ids["agents.audit.read"], ("SYSTEM_ADMIN", "RECTOR"))


def downgrade() -> None:
    bind = op.get_bind()
    permission_ids = bind.execute(sa.text("SELECT id FROM permissions WHERE key LIKE 'agents.%'")).scalars().all()
    for permission_id in permission_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key LIKE 'agents.%'"))
    op.execute("DROP FUNCTION IF EXISTS education_os_m25_has_permission(text)")
    for table in reversed(TABLES):
        op.drop_table(table)
