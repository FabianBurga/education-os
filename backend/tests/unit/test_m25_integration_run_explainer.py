from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.deps import CurrentPrincipal
from app.modules.agents.evidence import build_integration_run_evidence_pack
from app.modules.agents.integration_run_explainer import explain_integration_run
from app.modules.agents.models import AgentDefinition, AgentPolicyVersion, AgentRun
from app.modules.agents.planner import plan_advisor
from app.modules.agents.prompt_contract import ProviderExplanationOutput, ProviderFinding
from app.modules.agents.provider_execution import _validate_output
from app.modules.agents.providers import (
    FakeProvider,
    ProviderFailureCode,
    ProviderGatewayError,
    ProviderRequest,
)
from app.modules.agents.registry import known_agent, known_capability
from app.modules.agents.schemas import (
    AgentCountsRead,
    AgentEvidenceRead,
    AgentIssueRead,
    AgentProvenanceRead,
    IntegrationRunAdvisorOutput,
    IntegrationRunExplainerCreate,
    IntegrationRunExplainerOutput,
    ProviderFindingRead,
)
from app.modules.agents.verifier import verify_integration_run_explainer_output

ORG = UUID("dada4d4e-8854-5d09-8c21-c4516c06f5bb")
INST = UUID("ebda65b9-b77f-51d0-8263-f290fd0d24c0")
PRINCIPAL = CurrentPrincipal(user_id=uuid4(), organization_id=ORG, institution_id=INST)


def _base() -> IntegrationRunAdvisorOutput:
    run_id = uuid4()
    return IntegrationRunAdvisorOutput(
        run_id=run_id, status="COMPLETED", summary="safe", safe_next_action="review",
        counts=AgentCountsRead(total=3, valid=1, invalid=1, conflicts=1, applied=1, failed=0),
        issues=[AgentIssueRead(row_number=2, code="ACADEMIC_PERIOD_NOT_FOUND", category="INVALID", safe_explanation="safe")],
        provenance=AgentProvenanceRead(connector_key="m24.controlled", sanitized_filename="safe.csv", source_sha256="a" * 64),
        evidence_refs=[AgentEvidenceRead(reference_key="m24:run", source_module="integrations", source_entity_type="IntegrationRun", source_entity_id=run_id, provenance_sha256="a" * 64)],
    )


def _models() -> tuple[AgentRun, AgentDefinition, AgentPolicyVersion]:
    definition = AgentDefinition(organization_id=ORG, institution_id=INST, agent_key="integration_run_explainer", version=1, status="ENABLED", capability_keys_json=["integration.run.explain"], tool_keys_json=["m24.integration_run.inspect"], max_autonomy_level="L0")
    policy = AgentPolicyVersion(organization_id=ORG, institution_id=INST, policy_key="integration_run_explainer", version=1, status="ENABLED", max_autonomy_level="L0", max_steps=4, max_tool_calls=1, provider_policy="PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK")
    run = AgentRun(organization_id=ORG, institution_id=INST, actor_user_id=PRINCIPAL.user_id, agent_key="integration_run_explainer", agent_definition_id=definition.id, agent_definition_version=1, policy_id=policy.id, policy_version=1, request_type="M24_INTEGRATION_RUN_EXPLAIN", request_sha256="b" * 64, correlation_id=uuid4())
    return run, definition, policy


def test_explainer_registry_plan_and_closed_input_contract():
    assert known_agent("integration_run_explainer").tool_keys == ("m24.integration_run.inspect",)
    assert known_capability("integration.run.explain").required_permission == "integrations.view"
    assert [step.step_type for step in plan_advisor("integration_run_explainer")] == ["PLANNER", "POLICY", "EXECUTOR", "VERIFIER"]
    for focus in ("SUMMARY", "ERRORS", "OUTCOME"):
        assert IntegrationRunExplainerCreate(integration_run_id=uuid4(), explanation_focus=focus)
    with pytest.raises(ValidationError):
        IntegrationRunExplainerCreate(integration_run_id=uuid4(), explanation_focus="FREEFORM")
    with pytest.raises(ValidationError):
        IntegrationRunExplainerCreate.model_validate({"integration_run_id": str(uuid4()), "explanation_focus": "SUMMARY", "provider": "fake"})


def test_no_model_or_router_failure_uses_deterministic_fallback(monkeypatch):
    base = _base()
    run, definition, policy = _models()
    monkeypatch.setattr(
        "app.modules.agents.integration_run_explainer.route_provider_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)),
    )
    result = explain_integration_run(object(), PRINCIPAL, run=run, definition=definition, policy=policy, base=base, explanation_focus="ERRORS")
    assert result.output.explanation_mode == "DETERMINISTIC_FALLBACK"
    assert result.pack.agent_key == "integration_run_explainer"
    assert result.output.provider_failure_code == ProviderFailureCode.POLICY_BLOCK.value
    assert result.output.evidence_manifest_sha256 == result.pack.manifest_sha256
    assert "ACADEMIC_PERIOD_NOT_FOUND" in result.output.summary or result.output.key_findings


def test_fake_provider_result_is_wrapped_and_citations_are_verified(monkeypatch):
    base = _base()
    run, definition, policy = _models()
    decision = SimpleNamespace(provider_key="fake", max_estimated_cost_microusd=100)
    provider_output = ProviderExplanationOutput(summary="safe", key_findings=[ProviderFinding(text="finding", evidence_refs=["ev_01"])], caveats=[], evidence_refs=[])
    monkeypatch.setattr("app.modules.agents.integration_run_explainer.route_provider_model", lambda *args, **kwargs: decision)
    monkeypatch.setattr("app.modules.agents.integration_run_explainer.execute_fake_provider", lambda *args, **kwargs: SimpleNamespace(output=provider_output, fallback_used=False, failure_code=None, provider_call_id=uuid4()))
    result = explain_integration_run(object(), PRINCIPAL, run=run, definition=definition, policy=policy, base=base, explanation_focus="SUMMARY")
    assert result.output.explanation_mode == "FAKE_PROVIDER"
    # The service supplies the authoritative persisted audit row; direct unit
    # verification instead exercises the citation/mapping boundary below.


def test_default_fake_provider_output_has_one_valid_combined_citation():
    base = _base()
    pack = build_integration_run_evidence_pack(
        organization_id=ORG, institution_id=INST, output=base, agent_version=1, policy_version=1,
    )
    payload = FakeProvider().invoke(ProviderRequest("a" * 64, pack.manifest_sha256, {}, 128)).payload
    output = _validate_output(pack, payload)
    assert output.key_findings[0].evidence_refs == ["ev_01"]
    assert output.evidence_refs == []


def test_duplicate_fake_provider_citation_remains_rejected():
    base = _base()
    pack = build_integration_run_evidence_pack(
        organization_id=ORG, institution_id=INST, output=base, agent_version=1, policy_version=1,
    )
    payload = FakeProvider().invoke(ProviderRequest("a" * 64, pack.manifest_sha256, {}, 128)).payload
    payload["evidence_refs"] = ["ev_01"]
    with pytest.raises(ValueError, match="unknown or duplicate"):
        _validate_output(pack, payload)


def test_fabricated_citation_is_rejected_by_independent_verifier():
    base = _base()
    pack = build_integration_run_evidence_pack(organization_id=ORG, institution_id=INST, output=base, agent_version=1, policy_version=1)
    forged = IntegrationRunExplainerOutput(run_id=base.run_id, explanation_focus="SUMMARY", explanation_mode="DETERMINISTIC_FALLBACK", evidence_manifest_sha256=pack.manifest_sha256, summary="safe", key_findings=[ProviderFindingRead(text="forged", evidence_refs=["ev_99"])], caveats=[], evidence_refs=base.evidence_refs)
    with pytest.raises(HTTPException):
        verify_integration_run_explainer_output(
            forged,
            base=base,
            pack=pack,
            session=object(),
            agent_run=SimpleNamespace(),
            provider_call_id=None,
        )
