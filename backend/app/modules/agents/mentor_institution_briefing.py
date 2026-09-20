"""Governed L0 aggregate institutional Mentor briefing on the shared M25 path."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.budget import BudgetLimits
from app.modules.agents.evidence import (
    EvidencePack,
    build_mentor_institution_briefing_evidence_pack,
)
from app.modules.agents.models import AgentDefinition, AgentPolicyVersion, AgentRun
from app.modules.agents.prompt_contract import (
    MENTOR_INSTITUTION_BRIEFING_PROMPT,
    MentorInstitutionBriefingIntent,
    ProviderExplanationOutput,
    ProviderFinding,
    build_provider_prompt,
    validate_mentor_claims,
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
    InstitutionIntelligenceAdvisorOutput,
    MentorInstitutionBriefingOutput,
    ProviderFindingRead,
)

_DAY_BUDGET_MICROUSD = 1_000_000
_MONTH_BUDGET_MICROUSD = 10_000_000

_CATEGORY_LABELS = {
    "ATTENDANCE_RISK": "Riesgo de asistencia",
    "REPEATED_LATE": "Atrasos reiterados",
    "ACADEMIC_RISK": "Riesgo académico",
    "MISSING_WORK": "Trabajos pendientes",
}


def _category_labels(categories: list[str]) -> str:
    """Translate bounded M22 category keys without exposing future raw values."""
    labels = [_CATEGORY_LABELS.get(category, "Otra categoría institucional") for category in categories]
    return ", ".join(dict.fromkeys(labels)) or "ninguna"


def _freshness_label(freshness: str) -> str:
    if freshness == "CURRENT":
        return "vigente"
    if freshness.startswith("STALE_") and freshness.endswith("_DAYS"):
        days = freshness.removeprefix("STALE_").removesuffix("_DAYS")
        return f"desactualizada ({days} días de antigüedad)"
    return "no confirmada"


@dataclass(frozen=True, slots=True)
class MentorBriefingExecution:
    output: MentorInstitutionBriefingOutput
    pack: EvidencePack
    provider_call_id: object | None


def _fallback(base: InstitutionIntelligenceAdvisorOutput, focus: str) -> ProviderExplanationOutput:
    signals = base.signals
    categories = _category_labels(base.top_categories)
    freshness = _freshness_label(base.freshness)
    if focus == "PRIORITIES":
        summary = f"Las prioridades institucionales actuales incluyen {signals.high} señales de prioridad alta y {signals.medium} de prioridad media."
        finding = f"Las categorías actuales que requieren atención incluyen: {categories}."
    elif focus == "FOLLOW_UPS":
        summary = f"Se identifican {signals.high + signals.medium} señales de prioridad alta o media para revisión humana."
        finding = "Revise las categorías de prioridad alta y media mediante los procesos institucionales establecidos."
    else:
        summary = f"La institución registra {signals.total} señales abiertas: {signals.high} de prioridad alta, {signals.medium} media y {signals.low} baja."
        finding = f"La información está {freshness}. Las categorías actuales incluyen: {categories}."
    return ProviderExplanationOutput(
        summary=summary,
        key_findings=[ProviderFinding(text=finding, evidence_refs=["ev_01"])],
        caveats=["Este resumen utiliza únicamente información institucional agregada. Las decisiones permanecen bajo responsabilidad de las personas autorizadas."],
        evidence_refs=[],
    )


def _token_requirement(pack: EvidencePack) -> int:
    return max(1, (len(pack.canonical_semantic_json().encode("utf-8")) + 3) // 4)


def brief_institution(
    session: Session, principal: CurrentPrincipal, *, run: AgentRun, definition: AgentDefinition,
    policy: AgentPolicyVersion, base: InstitutionIntelligenceAdvisorOutput, briefing_focus: str,
) -> MentorBriefingExecution:
    """Use only eligible fake execution; all non-eligible paths remain deterministic."""
    pack = build_mentor_institution_briefing_evidence_pack(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        output=base, agent_version=definition.version, policy_version=policy.version,
    )
    def fallback() -> ProviderExplanationOutput:
        return _fallback(base, briefing_focus)
    try:
        decision = route_provider_model(
            session, principal, provider_policy=policy.provider_policy,
            requirements=RoutingRequirements(
                capability_class="EXPLANATION", required_input_tokens=_token_requirement(pack),
                required_output_tokens=256, per_run_cost_limit_microusd=1_000_000,
            ),
        )
        if decision.provider_key != "fake":
            raise ProviderGatewayError(ProviderFailureCode.POLICY_BLOCK)
        execution = execute_fake_provider(
            session, principal, run=run, decision=decision, provider_policy=policy.provider_policy,
            pack=pack, prompt_contract_sha256=MENTOR_INSTITUTION_BRIEFING_PROMPT.sha256,
            prompt=build_provider_prompt(
                contract=MENTOR_INSTITUTION_BRIEFING_PROMPT, pack=pack,
                intent=MentorInstitutionBriefingIntent(briefing_focus=briefing_focus),
            ),
            budget_limits=BudgetLimits(
                per_run_microusd=decision.max_estimated_cost_microusd,
                tenant_day_microusd=_DAY_BUDGET_MICROUSD, tenant_month_microusd=_MONTH_BUDGET_MICROUSD,
            ), adapters=ProviderAdapterRegistry(fake=FakeProvider()), deterministic_fallback=fallback,
            output_validator=validate_mentor_claims,
        )
        provider_output = execution.output or fallback()
        mode = "DETERMINISTIC_FALLBACK" if execution.fallback_used else "FAKE_PROVIDER"
        failure = execution.failure_code.value if execution.failure_code else None
        call_id = execution.provider_call_id
    except ProviderGatewayError as error:
        provider_output, mode, failure, call_id = fallback(), "DETERMINISTIC_FALLBACK", error.code.value, None
    return MentorBriefingExecution(
        output=MentorInstitutionBriefingOutput(
            briefing_focus=briefing_focus, explanation_mode=mode, provider_failure_code=failure,
            evidence_manifest_sha256=pack.manifest_sha256, snapshot_id=base.snapshot_id,
            snapshot_date=base.snapshot_date, freshness=base.freshness, summary=provider_output.summary,
            key_findings=[ProviderFindingRead(text=item.text, evidence_refs=item.evidence_refs) for item in provider_output.key_findings],
            caveats=provider_output.caveats, evidence_refs=base.evidence_refs,
        ), pack=pack, provider_call_id=call_id,
    )
