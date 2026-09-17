from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.agents.models import (
    AgentDefinition,
    AgentEvidenceRef,
    AgentPolicyVersion,
    AgentRun,
    AgentRunEvent,
    AgentRunStep,
    AgentToolCall,
)
from app.modules.agents.planner import plan_integration_run_advisor
from app.modules.agents.registry import known_agent, known_capability, known_tool
from app.modules.agents.schemas import (
    AgentCountsRead,
    AgentEvidenceRead,
    AgentProvenanceRead,
    AgentRunCreate,
    IntegrationRunAdvisorOutput,
)
from app.modules.agents.tools import _safe_explanation
from app.modules.agents.verifier import verify_integration_run_advisor_output

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0033_m25_agentic_control_plane.py"
ROUTER = ROOT / "app" / "modules" / "agents" / "router.py"
SERVICE = ROOT / "app" / "modules" / "agents" / "service.py"
TOOLS = ROOT / "app" / "modules" / "agents" / "tools.py"


def _output(*, total: int = 3, valid: int = 1, invalid: int = 1, conflicts: int = 1):
    run_id = uuid4()
    sha = "a" * 64
    return IntegrationRunAdvisorOutput(
        run_id=run_id, status="VALIDATED", summary="safe", safe_next_action="manual review",
        counts=AgentCountsRead(total=total, valid=valid, invalid=invalid, conflicts=conflicts, applied=0, failed=0),
        issues=[], provenance=AgentProvenanceRead(connector_key="m24.controlled.csv", sanitized_filename="safe.csv", source_sha256=sha),
        evidence_refs=[AgentEvidenceRead(reference_key=f"m24:integration_run:{run_id}", source_module="integrations",
                                         source_entity_type="IntegrationRun", source_entity_id=run_id, provenance_sha256=sha)],
    )


def test_m25_models_are_tenant_scoped_append_only_foundation_records():
    for model, table in (
        (AgentDefinition, "agent_definitions"), (AgentPolicyVersion, "agent_policy_versions"),
        (AgentRun, "agent_runs"), (AgentRunStep, "agent_run_steps"), (AgentToolCall, "agent_tool_calls"),
        (AgentEvidenceRef, "agent_evidence_refs"), (AgentRunEvent, "agent_run_events"),
    ):
        assert model.__tablename__ == table
        assert {"id", "organization_id", "institution_id", "created_at"}.issubset(model.model_fields)


def test_m25_code_owned_registries_fail_closed_for_unknown_keys():
    assert known_agent("integration_run_advisor").maximum_autonomy == "L0"
    assert known_capability("integration.run.inspect").required_permission == "integrations.view"
    assert known_tool("m24.integration_run.inspect").side_effect_class == "NONE"
    with pytest.raises(KeyError):
        known_agent("fabricated.agent")
    with pytest.raises(KeyError):
        known_capability("fabricated.capability")
    with pytest.raises(KeyError):
        known_tool("execute_sql")


def test_m25_request_schema_rejects_tenant_provider_tool_and_prompt_overrides():
    with pytest.raises(ValidationError):
        AgentRunCreate(integration_run_id=uuid4(), tenant_id=uuid4())
    with pytest.raises(ValidationError):
        AgentRunCreate(integration_run_id=uuid4(), tool_name="m24.integration_run.apply")
    with pytest.raises(ValidationError):
        AgentRunCreate(integration_run_id=uuid4(), provider="openai")


def test_m25_planner_is_deterministic_closed_and_allowlisted():
    plan = plan_integration_run_advisor(uuid4())
    assert tuple(step.step_type for step in plan) == ("PLANNER", "POLICY", "EXECUTOR", "VERIFIER")
    assert plan[2].tool_key == "m24.integration_run.inspect"
    assert all(step.tool_key in {None, "m24.integration_run.inspect"} for step in plan)


def test_m25_verifier_requires_coherent_counts_and_authoritative_evidence():
    verify_integration_run_advisor_output(_output())
    with pytest.raises(HTTPException):
        verify_integration_run_advisor_output(_output(total=2))


def test_m25_safe_error_explanations_are_deterministic_and_do_not_echo_raw_detail():
    assert "academic period" in _safe_explanation("ACADEMIC_PERIOD_NOT_FOUND").lower()
    assert _safe_explanation("unknown\\nSQL stack trace") == "The row requires manual review using its stable error code."


def test_m25_migration_creates_force_rls_append_only_tables_permissions_and_seeded_l0_definition():
    src = MIGRATION.read_text(encoding="utf-8")
    for table in ("agent_definitions", "agent_policy_versions", "agent_runs", "agent_run_steps", "agent_tool_calls", "agent_evidence_refs", "agent_run_events"):
        assert table in src
        assert "FORCE ROW LEVEL SECURITY" in src
    assert "agents.view" in src and "agents.use" in src and "agents.audit.read" in src
    assert "DETERMINISTIC_ONLY" in src
    assert "GRANT SELECT, INSERT" in src
    assert "GRANT SELECT, INSERT, UPDATE" not in src
    assert "DELETE" not in src.split("def downgrade", maxsplit=1)[0]


def test_m25_api_is_bounded_and_has_no_arbitrary_tool_provider_or_execution_surface():
    router = ROUTER.read_text(encoding="utf-8").lower()
    service = SERVICE.read_text(encoding="utf-8").lower()
    for expected in ("/integration_run_advisor/runs", "/runs/{run_id}/steps", "/runs/{run_id}/evidence", "/runs/{run_id}/tool-calls"):
        assert expected in router
    for forbidden in ("execute_sql", "/shell", "webhook", "credential", "/tools", "callback"):
        assert forbidden not in router
    assert "known_tool(\"m24.integration_run.inspect\")" in service
    assert "enqueue_canonical_event" in service


def test_m25_tool_gateway_uses_m24_service_not_sql_or_raw_payloads():
    src = TOOLS.read_text(encoding="utf-8")
    assert "get_run(session, principal, run_id)" in src
    assert "list_run_items(session, principal, run_id)" in src
    assert "list_run_events(session, principal, run_id)" in src
    assert "detail_json" not in src
    assert "text(" not in src
    assert "execute_sql" not in src
