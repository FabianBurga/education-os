from hashlib import sha256

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.agents.budget import reservation_key_for
from app.modules.agents.evidence import (
    EvidencePack,
    build_mentor_institution_briefing_evidence_pack,
    validate_provider_citations,
)
from app.modules.agents.models import AgentBudgetEvent, AgentProviderCall, AgentRun
from app.modules.agents.prompt_contract import (
    INTEGRATION_RUN_EXPLAINER_PROMPT,
    MENTOR_INSTITUTION_BRIEFING_PROMPT,
    ProviderExplanationOutput,
    validate_mentor_claims,
)
from app.modules.agents.provider_routing import (
    PROVIDER_OPTIONAL_POLICY,
    RoutingRequirements,
    route_provider_model,
)
from app.modules.agents.providers import ProviderGatewayError
from app.modules.agents.schemas import (
    AgentAdvisorOutput,
    InstitutionIntelligenceAdvisorOutput,
    IntegrationRunAdvisorOutput,
    IntegrationRunExplainerOutput,
    MentorInstitutionBriefingOutput,
    StudentTimelineAdvisorOutput,
)
from app.modules.m21_access import require_existing_student_scope


def verify_integration_run_advisor_output(output: IntegrationRunAdvisorOutput) -> None:
    counts = output.counts
    if counts.total != counts.valid + counts.invalid + counts.conflicts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if any(issue.category not in {"INVALID", "CONFLICT", "FAILED"} for issue in output.issues):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.provenance.source_sha256 != output.evidence_refs[0].provenance_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.evidence_refs[0].source_entity_id != output.run_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")


def verify_integration_run_explainer_output(
    output: IntegrationRunExplainerOutput,
    *,
    base: IntegrationRunAdvisorOutput,
    pack: EvidencePack,
    session: Session,
    agent_run: AgentRun,
    provider_call_id: object | None,
) -> None:
    verify_integration_run_advisor_output(base)
    if output.run_id != base.run_id or output.evidence_manifest_sha256 != pack.manifest_sha256:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.evidence_refs != base.evidence_refs or len(pack.citation_mapping) != len(output.evidence_refs):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    citations = [citation for finding in output.key_findings for citation in finding.evidence_refs]
    try:
        validate_provider_citations(pack, citations)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed") from exc
    if output.explanation_mode == "FAKE_PROVIDER":
        if provider_call_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        call = session.get(AgentProviderCall, provider_call_id)
        if (
            call is None
            or call.agent_run_id != agent_run.id
            or call.organization_id != agent_run.organization_id
            or call.institution_id != agent_run.institution_id
            or call.evidence_manifest_sha256 != pack.manifest_sha256
            or call.prompt_contract_sha256 != INTEGRATION_RUN_EXPLAINER_PROMPT.sha256
            or call.normalized_outcome != "SUCCEEDED"
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")


def verify_mentor_institution_briefing_output(
    output: MentorInstitutionBriefingOutput,
    *, base: InstitutionIntelligenceAdvisorOutput, pack: EvidencePack,
    session: Session, agent_run: AgentRun, provider_call_id: object | None,
) -> None:
    verify_institution_intelligence_advisor_output(base)
    expected_pack = build_mentor_institution_briefing_evidence_pack(
        organization_id=agent_run.organization_id, institution_id=agent_run.institution_id,
        output=base, agent_version=agent_run.agent_definition_version, policy_version=agent_run.policy_version,
    )
    if (
        output.snapshot_id != base.snapshot_id
        or output.snapshot_date != base.snapshot_date
        or output.freshness != base.freshness
        or output.evidence_manifest_sha256 != pack.manifest_sha256
        or output.evidence_refs != base.evidence_refs
        or len(pack.citation_mapping) != len(output.evidence_refs)
        or pack.manifest_sha256 != sha256(pack.canonical_semantic_json().encode("utf-8")).hexdigest()
        or pack.manifest_sha256 != expected_pack.manifest_sha256
        or pack.citation_mapping != expected_pack.citation_mapping
        or base.evidence_refs[0].source_entity_id != base.snapshot_id
        or base.evidence_refs[0].reference_key != f"m22:institution-snapshot:{base.snapshot_id}"
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    citations = [citation for finding in output.key_findings for citation in finding.evidence_refs]
    try:
        validate_provider_citations(pack, citations)
        if not citations:
            raise ValueError("Mentor briefing requires cited findings")
        validate_mentor_claims(ProviderExplanationOutput(
            summary=output.summary, key_findings=[item.model_dump() for item in output.key_findings],
            caveats=output.caveats, evidence_refs=[],
        ))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed") from exc
    if output.explanation_mode == "FAKE_PROVIDER":
        if provider_call_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        call = session.get(AgentProviderCall, provider_call_id)
        if (
            call is None or call.agent_run_id != agent_run.id
            or call.organization_id != agent_run.organization_id
            or call.institution_id != agent_run.institution_id
            or call.evidence_manifest_sha256 != pack.manifest_sha256
            or call.prompt_contract_sha256 != MENTOR_INSTITUTION_BRIEFING_PROMPT.sha256
            or call.normalized_outcome != "SUCCEEDED"
            or call.response_sha256 is None
            or call.normalized_error_code is not None
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        principal = CurrentPrincipal(user_id=agent_run.actor_user_id, organization_id=agent_run.organization_id, institution_id=agent_run.institution_id)
        try:
            decision = route_provider_model(
                session, principal, provider_policy=PROVIDER_OPTIONAL_POLICY,
                requirements=RoutingRequirements(
                    capability_class="EXPLANATION",
                    required_input_tokens=max(1, (len(pack.canonical_semantic_json().encode("utf-8")) + 3) // 4),
                    required_output_tokens=256, per_run_cost_limit_microusd=1_000_000,
                ),
            )
        except ProviderGatewayError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed") from exc
        if (
            call.model_registry_id != decision.model_config_id or call.provider_key != "fake"
            or call.provider_key != decision.provider_key or call.model_key != decision.model_key
            or call.model_version != decision.model_config_version
            or call.estimated_cost_microusd > decision.max_estimated_cost_microusd
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        reservation_key = reservation_key_for(run_id=agent_run.id, evidence_manifest_sha256=pack.manifest_sha256, model_config_id=decision.model_config_id)
        ledger = session.exec(select(AgentBudgetEvent).where(AgentBudgetEvent.agent_run_id == agent_run.id)).all()
        for scope in ("RUN", "TENANT_DAY", "TENANT_MONTH"):
            events = {row.event_type: row for row in ledger if row.budget_scope == scope}
            reserved, consumed, released = (events.get(kind) for kind in ("RESERVED", "CONSUMED", "RELEASED"))
            if (
                reserved is None or consumed is None
                or len(events) != sum(row.budget_scope == scope for row in ledger)
                or reserved.amount_microusd != decision.max_estimated_cost_microusd
                or consumed.amount_microusd != call.estimated_cost_microusd
                or consumed.provider_call_id != call.id
                or reserved.created_at > call.created_at
                or reserved.amount_microusd != consumed.amount_microusd + (released.amount_microusd if released else 0)
                or any(row.organization_id != agent_run.organization_id or row.institution_id != agent_run.institution_id
                       or row.provider_key != decision.provider_key or row.model_key != decision.model_key
                       or row.correlation_id != agent_run.correlation_id
                       or row.idempotency_key != f"{reservation_key}:{scope}:{row.event_type}" for row in events.values())
            ):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")


def _verify_evidence(output: AgentAdvisorOutput, source_module: str) -> None:
    if not output.evidence_refs:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    references = set()
    for evidence in output.evidence_refs:
        if evidence.source_module != source_module or not evidence.provenance_sha256:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        if evidence.reference_key in references:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
        references.add(evidence.reference_key)


def verify_student_timeline_advisor_output(
    output: StudentTimelineAdvisorOutput,
    *,
    session: Session | None = None,
    principal: CurrentPrincipal | None = None,
) -> None:
    if (session is None) != (principal is None):
        raise ValueError("Student timeline verification requires both session and principal")
    if session is not None and principal is not None:
        require_existing_student_scope(
            session,
            principal,
            output.student_id,
            permission_key="student_timeline.read",
        )
    if len(output.evidence_refs) > 26:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.followups.total > output.timeline.event_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if output.interventions.total > output.timeline.event_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    _verify_evidence(output, "student_timeline") if output.timeline.event_count else None


def verify_institution_intelligence_advisor_output(
    output: InstitutionIntelligenceAdvisorOutput,
) -> None:
    signals = output.signals
    if signals.total != signals.low + signals.medium + signals.high:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    if not output.provenance.policy_key or output.provenance.policy_version < 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
    _verify_evidence(output, "intelligence")


def verify_agent_output(
    output: AgentAdvisorOutput,
    *,
    session: Session | None = None,
    principal: CurrentPrincipal | None = None,
) -> None:
    if isinstance(output, IntegrationRunAdvisorOutput):
        verify_integration_run_advisor_output(output)
    elif isinstance(output, StudentTimelineAdvisorOutput):
        verify_student_timeline_advisor_output(output, session=session, principal=principal)
    elif isinstance(output, InstitutionIntelligenceAdvisorOutput):
        verify_institution_intelligence_advisor_output(output)
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent verification failed")
