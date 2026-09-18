"""Governed L0 integration-run explanation built on the shared M25 runtime."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.budget import BudgetLimits
from app.modules.agents.evidence import EvidencePack, build_integration_run_evidence_pack
from app.modules.agents.models import AgentDefinition, AgentPolicyVersion, AgentRun
from app.modules.agents.prompt_contract import (
    INTEGRATION_RUN_EXPLAINER_PROMPT,
    IntegrationRunExplanationIntent,
    ProviderExplanationOutput,
    ProviderFinding,
    build_provider_prompt,
)
from app.modules.agents.provider_execution import execute_fake_provider
from app.modules.agents.provider_routing import RoutingRequirements, route_provider_model
from app.modules.agents.providers import (
    FakeProvider,
    ProviderAdapterRegistry,
    ProviderFailureCode,
    ProviderGatewayError,
)
from app.modules.agents.schemas import (
    IntegrationRunAdvisorOutput,
    IntegrationRunExplainerOutput,
    ProviderFindingRead,
)

_DAY_BUDGET_MICROUSD = 1_000_000
_MONTH_BUDGET_MICROUSD = 10_000_000


@dataclass(frozen=True, slots=True)
class ExplainerExecution:
    output: IntegrationRunExplainerOutput
    pack: EvidencePack
    provider_call_id: object | None


def _fallback(
    base: IntegrationRunAdvisorOutput,
    focus: str,
) -> ProviderExplanationOutput:
    counts = base.counts
    if focus == "ERRORS":
        summary = f"The run has {counts.invalid} invalid rows and {counts.conflicts} conflicts."
        finding = f"Stable issue codes: {', '.join(sorted({issue.code for issue in base.issues})) or 'none'}."
    elif focus == "OUTCOME":
        summary = f"The run applied {counts.applied} rows and failed {counts.failed} rows."
        finding = f"Run status is {base.status}; {counts.total - counts.applied} rows were not applied."
    else:
        summary = f"The run is {base.status} with {counts.total} total rows and {counts.applied} applied rows."
        finding = f"Validation totals: {counts.valid} valid, {counts.invalid} invalid, {counts.conflicts} conflicts."
    return ProviderExplanationOutput(
        summary=summary,
        key_findings=[ProviderFinding(text=finding, evidence_refs=["ev_01"])],
        caveats=["This explanation is based only on the authorized integration run evidence."],
        evidence_refs=["ev_01"],
    )


def _token_requirement(pack: EvidencePack) -> int:
    return max(1, (len(pack.canonical_semantic_json().encode("utf-8")) + 3) // 4)


def explain_integration_run(
    session: Session,
    principal: CurrentPrincipal,
    *,
    run: AgentRun,
    definition: AgentDefinition,
    policy: AgentPolicyVersion,
    base: IntegrationRunAdvisorOutput,
    explanation_focus: str,
) -> ExplainerExecution:
    """Route only eligible fake execution; all other cases fall back safely."""
    pack = build_integration_run_evidence_pack(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        output=base,
        agent_version=definition.version,
        policy_version=policy.version,
        agent_key="integration_run_explainer",
    )
    def fallback() -> ProviderExplanationOutput:
        return _fallback(base, explanation_focus)
    intent = IntegrationRunExplanationIntent(explanation_focus=explanation_focus)
    try:
        decision = route_provider_model(
            session,
            principal,
            provider_policy=policy.provider_policy,
            requirements=RoutingRequirements(
                capability_class="EXPLANATION",
                required_input_tokens=_token_requirement(pack),
                required_output_tokens=256,
                per_run_cost_limit_microusd=1_000_000,
            ),
        )
        # Live and local keys intentionally never reach an executable adapter.
        if decision.provider_key != "fake":
            raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)
        execution = execute_fake_provider(
            session,
            principal,
            run=run,
            decision=decision,
            provider_policy=policy.provider_policy,
            pack=pack,
            prompt_contract_sha256=INTEGRATION_RUN_EXPLAINER_PROMPT.sha256,
            prompt=build_provider_prompt(
                contract=INTEGRATION_RUN_EXPLAINER_PROMPT, pack=pack, intent=intent,
            ),
            budget_limits=BudgetLimits(
                per_run_microusd=decision.max_estimated_cost_microusd,
                tenant_day_microusd=_DAY_BUDGET_MICROUSD,
                tenant_month_microusd=_MONTH_BUDGET_MICROUSD,
            ),
            adapters=ProviderAdapterRegistry(fake=FakeProvider()),
            deterministic_fallback=fallback,
        )
        provider_output = execution.output or fallback()
        mode = "DETERMINISTIC_FALLBACK" if execution.fallback_used else "FAKE_PROVIDER"
        failure = execution.failure_code.value if execution.failure_code else None
        provider_call_id = execution.provider_call_id
    except ProviderGatewayError as error:
        provider_output = fallback()
        mode = "DETERMINISTIC_FALLBACK"
        failure = error.code.value
        provider_call_id = None
    return ExplainerExecution(
        output=IntegrationRunExplainerOutput(
            run_id=base.run_id,
            explanation_focus=explanation_focus,
            explanation_mode=mode,
            provider_failure_code=failure,
            evidence_manifest_sha256=pack.manifest_sha256,
            summary=provider_output.summary,
            key_findings=[
                ProviderFindingRead(text=item.text, evidence_refs=item.evidence_refs)
                for item in provider_output.key_findings
            ],
            caveats=provider_output.caveats,
            evidence_refs=base.evidence_refs,
        ),
        pack=pack,
        provider_call_id=provider_call_id,
    )
