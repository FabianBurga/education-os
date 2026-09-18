"""Seed M25 L0 read-only advisor definitions and immutable policies.

Revision ID: 0034_m25_read_only_advisor_seed
Revises: 0033_m25_agentic_control_plane
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0034_m25_read_only_advisor_seed"
down_revision: str | None = "0033_m25_agentic_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADVISORS = (
    (
        "student_timeline_advisor",
        '["student.timeline.inspect"]',
        '["m21.student_timeline.inspect"]',
        '{"evidence_required":true,"provider_required":false,"side_effect_class":"NONE","verifier_required":true}',
        "M21_STUDENT_TIMELINE_INSPECT",
    ),
    (
        "institution_intelligence_advisor",
        '["intelligence.snapshot.inspect"]',
        '["m22.intelligence_snapshot.inspect"]',
        '{"evidence_required":true,"provider_required":false,"side_effect_class":"NONE","verifier_required":true}',
        "M22_INSTITUTION_INTELLIGENCE_INSPECT",
    ),
)
_AGENT_KEYS = "'integration_run_advisor','student_timeline_advisor','institution_intelligence_advisor'"
_TOOL_KEYS = "'m24.integration_run.inspect','m21.student_timeline.inspect','m22.intelligence_snapshot.inspect'"
_SOURCE_MODULES = "'integrations','student_timeline','intelligence'"
_REQUEST_TYPES = "'M24_INTEGRATION_RUN_INSPECT','M21_STUDENT_TIMELINE_INSPECT','M22_INSTITUTION_INTELLIGENCE_INSPECT'"


def upgrade() -> None:
    # 0033 intentionally constrained the first closed registry.  M25-2 keeps
    # that registry closed while extending it only to these two approved keys.
    op.drop_constraint("ck_agent_definitions_key", "agent_definitions", type_="check")
    op.create_check_constraint("ck_agent_definitions_key", "agent_definitions", f"agent_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_policy_versions_key", "agent_policy_versions", type_="check")
    op.create_check_constraint("ck_agent_policy_versions_key", "agent_policy_versions", f"policy_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_runs_key", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_key", "agent_runs", f"agent_key IN ({_AGENT_KEYS})")
    op.drop_constraint("ck_agent_runs_request_type", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_request_type", "agent_runs", f"request_type IN ({_REQUEST_TYPES})")
    op.drop_constraint("ck_agent_tool_calls_key", "agent_tool_calls", type_="check")
    op.create_check_constraint("ck_agent_tool_calls_key", "agent_tool_calls", f"tool_key IN ({_TOOL_KEYS})")
    op.drop_constraint("ck_agent_evidence_refs_source", "agent_evidence_refs", type_="check")
    op.create_check_constraint("ck_agent_evidence_refs_source", "agent_evidence_refs", f"source_module IN ({_SOURCE_MODULES})")

    bind = op.get_bind()
    tenants = bind.execute(
        sa.text(
            """
            SELECT organization_id, id
            FROM institutions
            WHERE status = 'ACTIVE'
            ORDER BY organization_id, id
            """
        )
    ).all()
    if not tenants:
        raise RuntimeError("M25-2 requires at least one active institution")

    for organization_id, institution_id in tenants:
        for agent_key, capabilities, tools, config, _request_type in _ADVISORS:
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
                    ON CONFLICT (institution_id, agent_key, version) DO NOTHING
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "agent_key": agent_key,
                    "capabilities": capabilities,
                    "tools": tools,
                    "config": config,
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
                        'ENABLED', 'L0', 4, 1, 'DETERMINISTIC_ONLY',
                        CAST(:config AS jsonb), NULL, NOW()
                    )
                    ON CONFLICT (institution_id, policy_key, version) DO NOTHING
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "institution_id": institution_id,
                    "policy_key": agent_key,
                    "config": config,
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    keys = [item[0] for item in _ADVISORS]
    referenced = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM agent_runs
            WHERE agent_key = ANY(CAST(:keys AS text[]))
            LIMIT 1
            """
        ),
        {"keys": keys},
    ).scalar_one_or_none()
    if referenced is not None:
        raise RuntimeError(
            "Cannot downgrade M25-2 advisor seed after execution audit exists"
        )

    bind.execute(
        sa.text(
            "DELETE FROM agent_policy_versions "
            "WHERE policy_key = ANY(CAST(:keys AS text[])) AND version = 1"
        ),
        {"keys": keys},
    )
    bind.execute(
        sa.text(
            "DELETE FROM agent_definitions "
            "WHERE agent_key = ANY(CAST(:keys AS text[])) AND version = 1"
        ),
        {"keys": keys},
    )

    op.drop_constraint("ck_agent_evidence_refs_source", "agent_evidence_refs", type_="check")
    op.create_check_constraint("ck_agent_evidence_refs_source", "agent_evidence_refs", "source_module = 'integrations'")
    op.drop_constraint("ck_agent_tool_calls_key", "agent_tool_calls", type_="check")
    op.create_check_constraint("ck_agent_tool_calls_key", "agent_tool_calls", "tool_key = 'm24.integration_run.inspect'")
    op.drop_constraint("ck_agent_runs_request_type", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_request_type", "agent_runs", "request_type = 'M24_INTEGRATION_RUN_INSPECT'")
    op.drop_constraint("ck_agent_runs_key", "agent_runs", type_="check")
    op.create_check_constraint("ck_agent_runs_key", "agent_runs", "agent_key = 'integration_run_advisor'")
    op.drop_constraint("ck_agent_policy_versions_key", "agent_policy_versions", type_="check")
    op.create_check_constraint("ck_agent_policy_versions_key", "agent_policy_versions", "policy_key = 'integration_run_advisor'")
    op.drop_constraint("ck_agent_definitions_key", "agent_definitions", type_="check")
    op.create_check_constraint("ck_agent_definitions_key", "agent_definitions", "agent_key = 'integration_run_advisor'")
