from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.agents.context import build_context_envelope
from app.modules.agents.executor import execute_inspection_tool
from app.modules.agents.integration_run_explainer import explain_integration_run
from app.modules.agents.mentor_institution_briefing import brief_institution
from app.modules.agents.models import (
    AgentDefinition,
    AgentEvidenceRef,
    AgentPolicyVersion,
    AgentRun,
    AgentRunEvent,
    AgentRunStep,
    AgentToolCall,
)
from app.modules.agents.planner import plan_advisor
from app.modules.agents.policy import evaluate_l0_policy, require_permission
from app.modules.agents.prompt_contract import MENTOR_INSTITUTION_BRIEFING_PROMPT
from app.modules.agents.registry import AGENTS, known_agent, known_tool
from app.modules.agents.schemas import (
    AgentAdvisorOutput,
    AgentDefinitionRead,
    AgentEvidenceRead,
    AgentRunRead,
    AgentRunStepRead,
    AgentToolCallRead,
    InstitutionIntelligenceAdvisorOutput,
    IntegrationRunAdvisorOutput,
    IntegrationRunExplainerOutput,
    MentorInstitutionBriefingOutput,
    StudentTimelineAdvisorOutput,
)
from app.modules.agents.verifier import (
    verify_agent_output,
    verify_integration_run_explainer_output,
    verify_mentor_institution_briefing_output,
)
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event
from app.modules.m21_access import require_existing_student_scope

_REQUEST_TYPES = {
    "integration_run_advisor": "M24_INTEGRATION_RUN_INSPECT",
    "student_timeline_advisor": "M21_STUDENT_TIMELINE_INSPECT",
    "institution_intelligence_advisor": "M22_INSTITUTION_INTELLIGENCE_INSPECT",
    "integration_run_explainer": "M24_INTEGRATION_RUN_EXPLAIN",
    "mentor_institution_briefing": "M26_INSTITUTION_BRIEFING",
}
_OUTPUT_TYPES = {
    "integration_run_advisor": IntegrationRunAdvisorOutput,
    "student_timeline_advisor": StudentTimelineAdvisorOutput,
    "institution_intelligence_advisor": InstitutionIntelligenceAdvisorOutput,
    "integration_run_explainer": IntegrationRunExplainerOutput,
    "mentor_institution_briefing": MentorInstitutionBriefingOutput,
}


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _append_event(
    session: Session,
    principal: CurrentPrincipal,
    run: AgentRun,
    event_type: str,
    metadata: dict,
) -> None:
    sequence = session.exec(
        select(AgentRunEvent.sequence)
        .where(AgentRunEvent.run_id == run.id)
        .order_by(AgentRunEvent.sequence.desc())
    ).first()
    session.add(
        AgentRunEvent(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            run_id=run.id,
            sequence=(int(sequence) if sequence is not None else 0) + 1,
            event_type=event_type,
            actor_user_id=principal.user_id,
            metadata_json=metadata,
        )
    )


def _definition_and_policy(
    session: Session,
    principal: CurrentPrincipal,
    agent_key: str,
) -> tuple[AgentDefinition, AgentPolicyVersion]:
    try:
        known = known_agent(agent_key)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found") from exc
    definition = session.exec(
        select(AgentDefinition)
        .where(
            AgentDefinition.organization_id == principal.organization_id,
            AgentDefinition.institution_id == principal.institution_id,
            AgentDefinition.agent_key == agent_key,
            AgentDefinition.status == "ENABLED",
        )
        .order_by(AgentDefinition.version.desc())
    ).first()
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found")
    if (
        tuple(definition.capability_keys_json) != known.capability_keys
        or tuple(definition.tool_keys_json) != known.tool_keys
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent definition registry mismatch")
    policy = session.exec(
        select(AgentPolicyVersion)
        .where(
            AgentPolicyVersion.organization_id == principal.organization_id,
            AgentPolicyVersion.institution_id == principal.institution_id,
            AgentPolicyVersion.policy_key == agent_key,
            AgentPolicyVersion.status == "ENABLED",
        )
        .order_by(AgentPolicyVersion.version.desc())
    ).first()
    expected_provider_policy = (
        "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK"
        if agent_key in {"integration_run_explainer", "mentor_institution_briefing"}
        else "DETERMINISTIC_ONLY"
    )
    if policy is None or policy.provider_policy != expected_provider_policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent policy not found")
    return definition, policy


def list_agent_definitions(session: Session, principal: CurrentPrincipal) -> list[AgentDefinitionRead]:
    require_permission(session, principal, "agents.view")
    rows = session.exec(
        select(AgentDefinition)
        .where(
            AgentDefinition.organization_id == principal.organization_id,
            AgentDefinition.institution_id == principal.institution_id,
            AgentDefinition.status == "ENABLED",
        )
        .order_by(AgentDefinition.agent_key, AgentDefinition.version.desc())
    ).all()
    seen: set[str] = set()
    result: list[AgentDefinitionRead] = []
    for row in rows:
        if row.agent_key in seen or row.agent_key not in AGENTS:
            continue
        seen.add(row.agent_key)
        result.append(
            AgentDefinitionRead(
                agent_key=row.agent_key,
                maximum_autonomy=row.max_autonomy_level,
                capability_keys=list(row.capability_keys_json),
                tool_keys=list(row.tool_keys_json),
            )
        )
    return result


def _output_from_event(run: AgentRun, event: AgentRunEvent | None) -> AgentAdvisorOutput | None:
    if event is None or event.event_type != "COMPLETED":
        return None
    output_type = _OUTPUT_TYPES.get(run.agent_key)
    if output_type is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent output registry mismatch")
    return output_type.model_validate(event.metadata_json.get("output"))


def _safe_summary(output: AgentAdvisorOutput) -> dict:
    if isinstance(output, IntegrationRunAdvisorOutput):
        return {"status": output.status, "counts": output.counts.model_dump()}
    if isinstance(output, IntegrationRunExplainerOutput):
        return {"mode": output.explanation_mode, "focus": output.explanation_focus}
    if isinstance(output, MentorInstitutionBriefingOutput):
        return {"mode": output.explanation_mode, "focus": output.briefing_focus, "snapshot_date": output.snapshot_date.isoformat()}
    if isinstance(output, StudentTimelineAdvisorOutput):
        return {"event_count": output.timeline.event_count, "intervention_count": output.interventions.total}
    if isinstance(output, InstitutionIntelligenceAdvisorOutput):
        return {"snapshot_date": output.snapshot_date.isoformat(), "signal_total": output.signals.total}
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent output registry mismatch")


def run_advisor(
    session: Session,
    principal: CurrentPrincipal,
    *,
    agent_key: str,
    entity_id: UUID | None,
    explanation_focus: str | None = None,
) -> AgentRunRead:
    request_type = _REQUEST_TYPES.get(agent_key)
    if request_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found")
    definition, policy = _definition_and_policy(session, principal, agent_key)
    context = build_context_envelope(
        session,
        principal,
        agent_key=agent_key,
        request_type=request_type,
        entity_id=entity_id,
    )
    if agent_key == "student_timeline_advisor" and entity_id is not None:
        require_permission(session, principal, "agents.use")
        require_existing_student_scope(
            session,
            principal,
            entity_id,
            permission_key="student_timeline.read",
        )
    preinspected: InstitutionIntelligenceAdvisorOutput | None = None
    snapshot_identity: dict[str, str] | None = None
    mentor_policy_decision = None
    if agent_key == "mentor_institution_briefing":
        # Resolve once through the closed M22 adapter before replay lookup; the
        # exact same typed result is reused by the executor below.
        require_permission(session, principal, "agents.use")
        require_permission(session, principal, "intelligence.read")
        mentor_plan = plan_advisor(agent_key)
        if (
            tuple(step.step_type for step in mentor_plan) != ("PLANNER", "POLICY", "EXECUTOR", "VERIFIER")
            or mentor_plan[2].tool_key != "m22.intelligence_snapshot.inspect"
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Planner produced forbidden steps")
        mentor_policy_decision = evaluate_l0_policy(
            session, principal, known_agent(agent_key), known_tool(mentor_plan[2].tool_key),
            policy_max_autonomy=policy.max_autonomy_level,
            max_steps=policy.max_steps, max_tool_calls=policy.max_tool_calls,
        )
        if not mentor_policy_decision.allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent policy denied")
        candidate = execute_inspection_tool(session, principal, agent_key=agent_key, entity_id=None)
        if not isinstance(candidate, InstitutionIntelligenceAdvisorOutput):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mentor evidence boundary mismatch")
        preinspected = candidate
        snapshot_identity = {
            "snapshot_id": str(candidate.snapshot_id),
            "provenance_sha256": candidate.evidence_refs[0].provenance_sha256,
            "prompt_contract_sha256": MENTOR_INSTITUTION_BRIEFING_PROMPT.sha256,
        }
    request_material = {
        "agent_key": agent_key,
        "request_type": request_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "explanation_focus": explanation_focus,
    }
    if agent_key == "mentor_institution_briefing":
        request_material.update({
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "actor_user_id": str(principal.user_id),
            "agent_definition_version": definition.version,
            "policy_version": policy.version,
            "snapshot_identity": snapshot_identity,
        })
    request_sha = _sha(request_material)
    existing = session.exec(
        select(AgentRun).where(
            AgentRun.institution_id == principal.institution_id,
            AgentRun.agent_key == agent_key,
            AgentRun.request_sha256 == request_sha,
        )
    ).first()
    if existing is not None:
        return get_agent_run(session, principal, existing.id)

    run = AgentRun(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        agent_key=agent_key,
        agent_definition_id=definition.id,
        agent_definition_version=definition.version,
        policy_id=policy.id,
        policy_version=policy.version,
        request_type=request_type,
        request_sha256=request_sha,
        correlation_id=context.correlation_id,
    )
    session.add(run)
    session.flush()
    _append_event(session, principal, run, "CREATED", {"request_type": request_type})
    session.add(
        AgentRunStep(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            run_id=run.id,
            sequence=1,
            step_type="PLANNER",
            status="COMPLETED",
            summary_json={"planner": "DETERMINISTIC"},
        )
    )
    plan = plan_advisor(agent_key)
    if (
        len(plan) != 4
        or tuple(step.step_type for step in plan) != ("PLANNER", "POLICY", "EXECUTOR", "VERIFIER")
        or plan[2].tool_key != definition.tool_keys_json[0]
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Planner produced forbidden steps")
    tool = known_tool(plan[2].tool_key)
    decision = mentor_policy_decision or evaluate_l0_policy(
        session,
        principal,
        known_agent(agent_key),
        tool,
        policy_max_autonomy=policy.max_autonomy_level,
        max_steps=policy.max_steps,
        max_tool_calls=policy.max_tool_calls,
    )
    if not decision.allowed:
        _append_event(session, principal, run, "FAILED", {"code": decision.code})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent policy denied")
    session.add(
        AgentRunStep(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            run_id=run.id,
            sequence=2,
            step_type="POLICY",
            status="ALLOWED",
            summary_json={"code": decision.code},
        )
    )
    _append_event(session, principal, run, "POLICY_ALLOWED", {"autonomy": "L0", "tool_key": tool.key})
    try:
        inspected = preinspected or execute_inspection_tool(
            session, principal, agent_key=agent_key, entity_id=entity_id,
        )
        if agent_key == "integration_run_explainer":
            if not isinstance(inspected, IntegrationRunAdvisorOutput) or explanation_focus is None:
                raise ValueError("Explainer requires authorized integration evidence and typed focus")
            explained = explain_integration_run(
                session,
                principal,
                run=run,
                definition=definition,
                policy=policy,
                base=inspected,
                explanation_focus=explanation_focus,
            )
            output = explained.output
        elif agent_key == "mentor_institution_briefing":
            if not isinstance(inspected, InstitutionIntelligenceAdvisorOutput) or explanation_focus is None:
                raise ValueError("Mentor requires authorized M22 evidence and typed focus")
            explained = brief_institution(
                session, principal, run=run, definition=definition, policy=policy,
                base=inspected, briefing_focus=explanation_focus,
            )
            output = explained.output
        else:
            output = inspected
        output_payload = output.model_dump(mode="json")
        session.add(
            AgentRunStep(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                run_id=run.id,
                sequence=3,
                step_type="EXECUTOR",
                status="COMPLETED",
                summary_json={"tool_key": tool.key},
            )
        )
        for evidence in output.evidence_refs:
            session.add(
                AgentEvidenceRef(
                    organization_id=principal.organization_id,
                    institution_id=principal.institution_id,
                    run_id=run.id,
                    reference_key=evidence.reference_key,
                    source_module=evidence.source_module,
                    source_entity_type=evidence.source_entity_type,
                    source_entity_id=evidence.source_entity_id,
                    provenance_sha256=evidence.provenance_sha256,
                )
            )
        if agent_key == "integration_run_explainer":
            verify_integration_run_explainer_output(
                output,
                base=inspected,
                pack=explained.pack,
                session=session,
                agent_run=run,
                provider_call_id=explained.provider_call_id,
            )
        elif agent_key == "mentor_institution_briefing":
            verify_mentor_institution_briefing_output(
                output, base=inspected, pack=explained.pack, session=session,
                agent_run=run, provider_call_id=explained.provider_call_id,
            )
        else:
            verify_agent_output(output, session=session, principal=principal)
        session.add(
            AgentToolCall(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                run_id=run.id,
                sequence=1,
                tool_key=tool.key,
                schema_version=tool.input_schema_version,
                input_sha256=_sha(request_material),
                output_sha256=_sha(output_payload),
                verification_status="VERIFIED",
                safe_summary_json=_safe_summary(output),
            )
        )
        session.add(
            AgentRunStep(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                run_id=run.id,
                sequence=4,
                step_type="VERIFIER",
                status="VERIFIED",
                summary_json={"evidence_refs": len(output.evidence_refs)},
            )
        )
        _append_event(session, principal, run, "COMPLETED", {"output": output_payload})
        record_audit(
            session,
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action="AGENT_RUN_COMPLETED",
            entity_type="AgentRun",
            entity_id=run.id,
            metadata={"agent_key": agent_key, "correlation_id": str(run.correlation_id)},
        )
        enqueue_canonical_event(
            session,
            institution_id=principal.institution_id,
            event_type="agent.run.completed",
            event_version=1,
            aggregate_type="agent_run",
            aggregate_id=run.id,
            actor_user_id=principal.user_id,
            correlation_id=run.correlation_id,
            payload={"agent_key": agent_key, "status": "COMPLETED"},
        )
    except (HTTPException, ValueError):
        _append_event(session, principal, run, "FAILED", {"code": "VERIFICATION_OR_TOOL_FAILURE"})
        enqueue_canonical_event(
            session,
            institution_id=principal.institution_id,
            event_type="agent.run.failed",
            event_version=1,
            aggregate_type="agent_run",
            aggregate_id=run.id,
            actor_user_id=principal.user_id,
            correlation_id=run.correlation_id,
            payload={"agent_key": agent_key, "status": "FAILED"},
        )
        record_audit(
            session,
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action="AGENT_RUN_FAILED",
            entity_type="AgentRun",
            entity_id=run.id,
            metadata={"agent_key": agent_key, "correlation_id": str(run.correlation_id)},
        )
        session.flush()
        return get_agent_run(session, principal, run.id)
    session.flush()
    return get_agent_run(session, principal, run.id)


def run_integration_run_advisor(
    session: Session,
    principal: CurrentPrincipal,
    *,
    integration_run_id: UUID,
) -> AgentRunRead:
    return run_advisor(
        session, principal, agent_key="integration_run_advisor", entity_id=integration_run_id,
    )


def run_integration_run_explainer(
    session: Session,
    principal: CurrentPrincipal,
    *,
    integration_run_id: UUID,
    explanation_focus: str,
) -> AgentRunRead:
    return run_advisor(
        session,
        principal,
        agent_key="integration_run_explainer",
        entity_id=integration_run_id,
        explanation_focus=explanation_focus,
    )


def run_student_timeline_advisor(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_id: UUID,
) -> AgentRunRead:
    return run_advisor(
        session, principal, agent_key="student_timeline_advisor", entity_id=student_id,
    )


def run_institution_intelligence_advisor(
    session: Session,
    principal: CurrentPrincipal,
) -> AgentRunRead:
    return run_advisor(
        session, principal, agent_key="institution_intelligence_advisor", entity_id=None,
    )


def run_mentor_institution_briefing(
    session: Session, principal: CurrentPrincipal, *, briefing_focus: str,
) -> AgentRunRead:
    return run_advisor(
        session, principal, agent_key="mentor_institution_briefing", entity_id=None,
        explanation_focus=briefing_focus,
    )


def _latest_event(session: Session, run_id: UUID) -> AgentRunEvent | None:
    return session.exec(
        select(AgentRunEvent)
        .where(AgentRunEvent.run_id == run_id)
        .order_by(AgentRunEvent.sequence.desc())
    ).first()


def get_agent_run(session: Session, principal: CurrentPrincipal, run_id: UUID) -> AgentRunRead:
    require_permission(session, principal, "agents.view")
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    latest = _latest_event(session, run.id)
    return AgentRunRead(
        id=run.id,
        agent_key=run.agent_key,
        request_type=run.request_type,
        status=latest.event_type if latest is not None else "CREATED",
        correlation_id=run.correlation_id,
        created_at=run.created_at,
        output=_output_from_event(run, latest),
    )


def list_agent_runs(session: Session, principal: CurrentPrincipal, *, limit: int = 100) -> list[AgentRunRead]:
    require_permission(session, principal, "agents.view")
    rows = session.exec(
        select(AgentRun)
        .where(
            AgentRun.organization_id == principal.organization_id,
            AgentRun.institution_id == principal.institution_id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    ).all()
    return [get_agent_run(session, principal, row.id) for row in rows]


def list_agent_steps(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentRunStepRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [
        AgentRunStepRead(sequence=row.sequence, step_type=row.step_type, status=row.status, created_at=row.created_at)
        for row in session.exec(
            select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.sequence).limit(100)
        ).all()
    ]


def list_agent_evidence(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentEvidenceRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [
        AgentEvidenceRead(
            reference_key=row.reference_key,
            source_module=row.source_module,
            source_entity_type=row.source_entity_type,
            source_entity_id=row.source_entity_id,
            provenance_sha256=row.provenance_sha256,
        )
        for row in session.exec(
            select(AgentEvidenceRef).where(AgentEvidenceRef.run_id == run_id).order_by(AgentEvidenceRef.created_at).limit(100)
        ).all()
    ]


def list_agent_tool_calls(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentToolCallRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [
        AgentToolCallRead(
            sequence=row.sequence,
            tool_key=row.tool_key,
            schema_version=row.schema_version,
            verification_status=row.verification_status,
            created_at=row.created_at,
        )
        for row in session.exec(
            select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.sequence).limit(100)
        ).all()
    ]
