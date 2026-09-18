"""Seed the M25 provider-optional integration run explainer.

Revision ID: 0036_m25_run_explainer
Revises: 0035_m25_governed_provider_exec

This configuration migration does not enable any provider or persist model
credentials.  The future explainer remains L0 and requires deterministic
fallback when no eligible model configuration is available.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0036_m25_run_explainer"
down_revision: str | None = "0035_m25_governed_provider_exec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENT_KEY = "integration_run_explainer"
_REQUEST_TYPE = "M24_INTEGRATION_RUN_EXPLAIN"
_CAPABILITY = "integration.run.explain"
_TOOL = "m24.integration_run.inspect"
_PILOT_TENANT_NAMES = (
    "Universidad de Otavalo",
    "Education OS Local Isolation Secondary",
)
_AGENT_KEYS = (
    "'integration_run_advisor','student_timeline_advisor',"
    "'institution_intelligence_advisor','integration_run_explainer'"
)
_REQUEST_TYPES = (
    "'M24_INTEGRATION_RUN_INSPECT','M21_STUDENT_TIMELINE_INSPECT',"
    "'M22_INSTITUTION_INTELLIGENCE_INSPECT','M24_INTEGRATION_RUN_EXPLAIN'"
)
_DEFINITION_CONFIG = (
    '{"deterministic_fallback_required":true,"evidence_required":true,'
    '"explanation_focus_values":["SUMMARY","ERRORS","OUTCOME"],'
    '"provider_required":false,"request_type":"M24_INTEGRATION_RUN_EXPLAIN",'
    '"side_effect_class":"NONE","verifier_required":true}'
)
_POLICY_CONFIG = (
    '{"allowed_capabilities":["integration.run.explain"],'
    '"allowed_tools":["m24.integration_run.inspect"],'
    '"budget_admission_required":true,"deterministic_fallback_required":true,'
    '"evidence_required":true,"provider_router_required":true,'
    '"side_effect_class":"NONE","verifier_required":true}'
)


def _pilot_tenants(bind: sa.Connection) -> list[tuple[object, object, str]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT organization_id, id, name
            FROM institutions
            WHERE status = 'ACTIVE' AND name = ANY(CAST(:names AS text[]))
            ORDER BY name
            """
        ),
        {"names": list(_PILOT_TENANT_NAMES)},
    ).all()
    if len(rows) != len(_PILOT_TENANT_NAMES) or {row.name for row in rows} != set(_PILOT_TENANT_NAMES):
        raise RuntimeError("M25-3C requires exactly the two existing controlled-pilot institutions")
    return rows


def upgrade() -> None:
    # 0035 intentionally froze the semantic enum before the first optional
    # provider policy was seeded. Widening is additive and preserves every
    # existing DETERMINISTIC_ONLY row without rewriting it.
    op.alter_column(
        "agent_policy_versions",
        "provider_policy",
        existing_type=sa.String(length=40),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.drop_constraint("ck_agent_policy_versions_provider", "agent_policy_versions", type_="check")
    op.create_check_constraint(
        "ck_agent_policy_versions_provider",
        "agent_policy_versions",
        "provider_policy IN ('DETERMINISTIC_ONLY','PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK')",
    )
    # Keep the registry closed while making the explicitly approved L0 agent
    # and its typed request kind representable. Existing advisor rows are not
    # touched and retain DETERMINISTIC_ONLY policies.
    op.drop_constraint("ck_agent_definitions_key", "agent_definitions", type_="check")
    op.create_check_constraint("ck_agent_definitions_key", "agent_definitions", f"agent_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_policy_versions_key", "agent_policy_versions", type_="check")
    op.create_check_constraint("ck_agent_policy_versions_key", "agent_policy_versions", f"policy_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_runs_key", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_key", "agent_runs", f"agent_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_runs_request_type", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_request_type", "agent_runs", f"request_type IN ({_REQUEST_TYPES})")

    bind = op.get_bind()
    for organization_id, institution_id, _name in _pilot_tenants(bind):
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_definitions (
                    id, organization_id, institution_id, agent_key, version,
                    status, capability_keys_json, tool_keys_json,
                    max_autonomy_level, config_json, created_by_user_id, created_at
                )
                VALUES (
                    :id, :organization_id, :institution_id, :agent_key, 1,
                    'ENABLED', CAST(:capabilities AS jsonb), CAST(:tools AS jsonb),
                    'L0', CAST(:config AS jsonb), NULL, NOW()
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "institution_id": institution_id,
                "agent_key": _AGENT_KEY,
                "capabilities": f'["{_CAPABILITY}"]',
                "tools": f'["{_TOOL}"]',
                "config": _DEFINITION_CONFIG,
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO agent_policy_versions (
                    id, organization_id, institution_id, policy_key, version,
                    status, max_autonomy_level, max_steps, max_tool_calls,
                    provider_policy, config_json, created_by_user_id, created_at
                )
                VALUES (
                    :id, :organization_id, :institution_id, :policy_key, 1,
                    'ENABLED', 'L0', 4, 1,
                    'PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK',
                    CAST(:config AS jsonb), NULL, NOW()
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "institution_id": institution_id,
                "policy_key": _AGENT_KEY,
                "config": _POLICY_CONFIG,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    referenced = bind.execute(
        sa.text("SELECT 1 FROM agent_runs WHERE agent_key = :agent_key LIMIT 1"),
        {"agent_key": _AGENT_KEY},
    ).scalar_one_or_none()
    if referenced is not None:
        raise RuntimeError("Cannot downgrade M25-3C explainer seed after execution audit exists")

    bind.execute(
        sa.text(
            "DELETE FROM agent_policy_versions "
            "WHERE policy_key = :agent_key AND version = 1"
        ),
        {"agent_key": _AGENT_KEY},
    )
    bind.execute(
        sa.text(
            "DELETE FROM agent_definitions "
            "WHERE agent_key = :agent_key AND version = 1"
        ),
        {"agent_key": _AGENT_KEY},
    )

    prior_agent_keys = (
        "'integration_run_advisor','student_timeline_advisor','institution_intelligence_advisor'"
    )
    prior_request_types = (
        "'M24_INTEGRATION_RUN_INSPECT','M21_STUDENT_TIMELINE_INSPECT',"
        "'M22_INSTITUTION_INTELLIGENCE_INSPECT'"
    )
    op.drop_constraint("ck_agent_runs_request_type", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_request_type", "agent_runs", f"request_type IN ({prior_request_types})")
    op.drop_constraint("ck_agent_runs_key", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_key", "agent_runs", f"agent_key IN ({prior_agent_keys})")
    op.drop_constraint("ck_agent_policy_versions_key", "agent_policy_versions", type_="check")
    op.create_check_constraint("ck_agent_policy_versions_key", "agent_policy_versions", f"policy_key IN ({prior_agent_keys})")
    op.drop_constraint("ck_agent_definitions_key", "agent_definitions", type_="check")
    op.create_check_constraint("ck_agent_definitions_key", "agent_definitions", f"agent_key IN ({prior_agent_keys})")
    long_policy_value = bind.execute(
        sa.text(
            "SELECT 1 FROM agent_policy_versions "
            "WHERE char_length(provider_policy) > 40 LIMIT 1"
        )
    ).scalar_one_or_none()
    if long_policy_value is not None:
        raise RuntimeError("Cannot narrow provider policy column while values exceed 40 characters")
    op.alter_column(
        "agent_policy_versions",
        "provider_policy",
        existing_type=sa.String(length=64),
        type_=sa.String(length=40),
        existing_nullable=False,
    )
