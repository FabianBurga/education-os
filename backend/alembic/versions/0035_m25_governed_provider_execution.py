"""Prepare append-only governed provider execution primitives for M25.

Revision ID: 0035_m25_governed_provider_exec
Revises: 0034_m25_read_only_advisor_seed

This migration is intentionally configuration/audit only: it stores neither
credentials nor raw prompts/responses and does not enable live providers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035_m25_governed_provider_exec"
down_revision: str | None = "0034_m25_read_only_advisor_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"
TABLES = ("agent_model_registry", "agent_provider_calls", "agent_budget_events")


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def upgrade() -> None:
    # Existing advisor policies retain DETERMINISTIC_ONLY.  This merely makes a
    # future explicitly seeded fallback policy representable.
    op.drop_constraint("ck_agent_policy_versions_provider", "agent_policy_versions", type_="check")
    op.create_check_constraint(
        "ck_agent_policy_versions_provider", "agent_policy_versions",
        "provider_policy IN ('DETERMINISTIC_ONLY','PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK')",
    )
    op.create_unique_constraint(
        "uq_agent_runs_tenant_identity",
        "agent_runs",
        ["id", "organization_id", "institution_id"],
    )
    op.create_table(
        "agent_model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("provider_key", sa.String(40), nullable=False), sa.Column("model_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("capability_class", sa.String(40), nullable=False), sa.Column("routing_priority", sa.Integer(), nullable=False),
        sa.Column("context_limit", sa.Integer(), nullable=False), sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False), sa.Column("max_estimated_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False), sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("max_fallbacks", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider_key IN ('fake','openai','anthropic','local')", name="ck_agent_model_registry_provider"),
        sa.CheckConstraint("version >= 1", name="ck_agent_model_registry_version"),
        sa.CheckConstraint("status IN ('ENABLED','DISABLED')", name="ck_agent_model_registry_status"),
        sa.CheckConstraint("capability_class = 'EXPLANATION'", name="ck_agent_model_registry_capability"),
        sa.CheckConstraint("routing_priority >= 1 AND context_limit >= 1 AND max_input_tokens >= 1 AND max_output_tokens >= 1 AND max_input_tokens + max_output_tokens <= context_limit", name="ck_agent_model_registry_limits"),
        sa.CheckConstraint("max_estimated_cost_microusd >= 0 AND timeout_seconds >= 1 AND max_attempts BETWEEN 1 AND 3 AND max_fallbacks BETWEEN 0 AND 2", name="ck_agent_model_registry_budget"),
        sa.UniqueConstraint("id", "organization_id", "institution_id", name="uq_agent_model_registry_tenant_identity"),
        sa.UniqueConstraint("institution_id", "provider_key", "model_key", "version", name="uq_agent_model_registry_version"),
    )
    op.create_table(
        "agent_provider_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_registry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False), sa.Column("provider_key", sa.String(40), nullable=False),
        sa.Column("model_key", sa.String(120), nullable=False), sa.Column("model_version", sa.Integer(), nullable=False),
        sa.Column("evidence_manifest_sha256", sa.String(64), nullable=False), sa.Column("prompt_contract_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False), sa.Column("response_sha256", sa.String(64)),
        sa.Column("input_tokens", sa.Integer()), sa.Column("output_tokens", sa.Integer()), sa.Column("estimated_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("latency_ms", sa.Integer()), sa.Column("normalized_outcome", sa.String(30), nullable=False),
        sa.Column("normalized_error_code", sa.String(60)),
        sa.Column("fallback_parent_call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number >= 1 AND model_version >= 1", name="ck_agent_provider_calls_attempt"),
        sa.CheckConstraint("provider_key IN ('fake','openai','anthropic','local')", name="ck_agent_provider_calls_provider"),
        sa.CheckConstraint("evidence_manifest_sha256 ~ '^[0-9a-f]{64}$' AND prompt_contract_sha256 ~ '^[0-9a-f]{64}$' AND request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_provider_calls_hashes"),
        sa.CheckConstraint("response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'", name="ck_agent_provider_calls_response_hash"),
        sa.CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_agent_provider_calls_input_tokens"),
        sa.CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_agent_provider_calls_output_tokens"),
        sa.CheckConstraint("estimated_cost_microusd >= 0 AND (latency_ms IS NULL OR latency_ms >= 0)", name="ck_agent_provider_calls_cost"),
        sa.CheckConstraint("normalized_outcome IN ('SUCCEEDED','FAILED','FALLBACK')", name="ck_agent_provider_calls_outcome"),
        sa.CheckConstraint("normalized_error_code IS NULL OR normalized_error_code IN ('PROVIDER_AUTH','PROVIDER_RATE_LIMIT','PROVIDER_TIMEOUT','PROVIDER_UNAVAILABLE','PROVIDER_INVALID_RESPONSE','PROVIDER_BUDGET_EXCEEDED','PROVIDER_POLICY_BLOCK','PROVIDER_CONTEXT_TOO_LARGE','PROVIDER_FALLBACK_EXHAUSTED')", name="ck_agent_provider_calls_error"),
        sa.ForeignKeyConstraint(["agent_run_id", "organization_id", "institution_id"], ["agent_runs.id", "agent_runs.organization_id", "agent_runs.institution_id"], name="fk_agent_provider_calls_run_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_registry_id", "organization_id", "institution_id"], ["agent_model_registry.id", "agent_model_registry.organization_id", "agent_model_registry.institution_id"], name="fk_agent_provider_calls_model_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fallback_parent_call_id", "organization_id", "institution_id"], ["agent_provider_calls.id", "agent_provider_calls.organization_id", "agent_provider_calls.institution_id"], name="fk_agent_provider_calls_fallback_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "organization_id", "institution_id", name="uq_agent_provider_calls_tenant_identity"),
        sa.UniqueConstraint("agent_run_id", "attempt_number", name="uq_agent_provider_calls_attempt"),
    )
    op.create_table(
        "agent_budget_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), *_tenant_columns(),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("agent_key", sa.String(120), nullable=False), sa.Column("provider_key", sa.String(40)), sa.Column("model_key", sa.String(120)),
        sa.Column("event_type", sa.String(20), nullable=False), sa.Column("budget_scope", sa.String(20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False), sa.Column("amount_microusd", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False), sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('RESERVED','CONSUMED','RELEASED')", name="ck_agent_budget_events_type"),
        sa.CheckConstraint("budget_scope IN ('RUN','TENANT_DAY','TENANT_MONTH')", name="ck_agent_budget_events_scope"),
        sa.CheckConstraint("amount_microusd >= 0", name="ck_agent_budget_events_amount"),
        sa.ForeignKeyConstraint(["agent_run_id", "organization_id", "institution_id"], ["agent_runs.id", "agent_runs.organization_id", "agent_runs.institution_id"], name="fk_agent_budget_events_run_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_call_id", "organization_id", "institution_id"], ["agent_provider_calls.id", "agent_provider_calls.organization_id", "agent_provider_calls.institution_id"], name="fk_agent_budget_events_provider_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("institution_id", "idempotency_key", name="uq_agent_budget_events_idempotency"),
    )
    for table in TABLES:
        op.create_index(f"ix_{table}_tenant", table, ["organization_id", "institution_id", "created_at"])
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        grant = "SELECT" if table == "agent_model_registry" else "SELECT, INSERT"
        op.execute(f'GRANT {grant} ON "{table}" TO education_app')
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT TO education_app USING ({TENANT} AND education_os_m25_has_permission('agents.view'))")
    op.create_index("ix_agent_model_registry_routing", "agent_model_registry", ["organization_id", "institution_id", "status", "capability_class", "routing_priority"])
    op.create_index("ix_agent_provider_calls_run", "agent_provider_calls", ["organization_id", "institution_id", "agent_run_id", "attempt_number"])
    op.create_index("ix_agent_provider_calls_provider", "agent_provider_calls", ["organization_id", "institution_id", "provider_key", "model_key", "created_at"])
    op.create_index("ix_agent_budget_events_period", "agent_budget_events", ["organization_id", "institution_id", "budget_scope", "period_start"])
    op.create_index("ix_agent_budget_events_run", "agent_budget_events", ["organization_id", "institution_id", "agent_run_id", "created_at"])
    op.create_index("ix_agent_budget_events_correlation", "agent_budget_events", ["organization_id", "institution_id", "correlation_id"])
    op.execute(
        "CREATE POLICY agent_provider_calls_insert ON agent_provider_calls FOR INSERT TO education_app WITH CHECK "
        f"({TENANT} AND EXISTS (SELECT 1 FROM agent_runs r WHERE r.id=agent_run_id "
        f"AND r.organization_id=organization_id AND r.institution_id=institution_id AND r.actor_user_id={USER_CTX}) "
        "AND EXISTS (SELECT 1 FROM agent_model_registry m WHERE m.id=model_registry_id "
        "AND m.organization_id=organization_id AND m.institution_id=institution_id) "
        "AND (fallback_parent_call_id IS NULL OR EXISTS (SELECT 1 FROM agent_provider_calls p "
        "WHERE p.id=fallback_parent_call_id AND p.agent_run_id=agent_run_id "
        "AND p.organization_id=organization_id AND p.institution_id=institution_id)) "
        "AND education_os_m25_has_permission('agents.use'))"
    )
    op.execute(
        "CREATE POLICY agent_budget_events_insert ON agent_budget_events FOR INSERT TO education_app WITH CHECK "
        f"({TENANT} AND EXISTS (SELECT 1 FROM agent_runs r WHERE r.id=agent_run_id "
        f"AND r.organization_id=organization_id AND r.institution_id=institution_id AND r.actor_user_id={USER_CTX}) "
        "AND (provider_call_id IS NULL OR EXISTS (SELECT 1 FROM agent_provider_calls p "
        "WHERE p.id=provider_call_id AND p.agent_run_id=agent_run_id "
        "AND p.organization_id=organization_id AND p.institution_id=institution_id)) "
        "AND education_os_m25_has_permission('agents.use'))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        if bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).scalar_one_or_none() is not None:
            raise RuntimeError("Cannot downgrade M25 provider execution after immutable configuration or audit exists")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_constraint("uq_agent_runs_tenant_identity", "agent_runs", type_="unique")
    op.drop_constraint("ck_agent_policy_versions_provider", "agent_policy_versions", type_="check")
    op.create_check_constraint("ck_agent_policy_versions_provider", "agent_policy_versions", "provider_policy = 'DETERMINISTIC_ONLY'")
