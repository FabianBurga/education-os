from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.agents.context import build_context_envelope
from app.modules.agents.executor import execute_inspection_tool
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
from app.modules.agents.policy import evaluate_l0_policy, require_permission
from app.modules.agents.registry import AGENTS, known_agent, known_tool
from app.modules.agents.schemas import (
    AgentDefinitionRead,
    AgentEvidenceRead,
    AgentRunRead,
    AgentRunStepRead,
    AgentToolCallRead,
    IntegrationRunAdvisorOutput,
)
from app.modules.agents.verifier import verify_integration_run_advisor_output
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _append_event(session: Session, principal: CurrentPrincipal, run: AgentRun, event_type: str, metadata: dict) -> None:
    sequence = session.exec(select(AgentRunEvent.sequence).where(AgentRunEvent.run_id == run.id).order_by(AgentRunEvent.sequence.desc())).first()
    session.add(AgentRunEvent(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        run_id=run.id, sequence=(int(sequence) if sequence is not None else 0) + 1,
        event_type=event_type, actor_user_id=principal.user_id, metadata_json=metadata,
    ))


def _definition_and_policy(session: Session, principal: CurrentPrincipal, agent_key: str) -> tuple[AgentDefinition, AgentPolicyVersion]:
    known = known_agent(agent_key)
    definition = session.exec(select(AgentDefinition).where(
        AgentDefinition.organization_id == principal.organization_id,
        AgentDefinition.institution_id == principal.institution_id,
        AgentDefinition.agent_key == agent_key, AgentDefinition.status == "ENABLED",
    ).order_by(AgentDefinition.version.desc())).first()
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent definition not found")
    if tuple(definition.capability_keys_json) != known.capability_keys or tuple(definition.tool_keys_json) != known.tool_keys:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent definition registry mismatch")
    policy = session.exec(select(AgentPolicyVersion).where(
        AgentPolicyVersion.organization_id == principal.organization_id,
        AgentPolicyVersion.institution_id == principal.institution_id,
        AgentPolicyVersion.policy_key == agent_key, AgentPolicyVersion.status == "ENABLED",
    ).order_by(AgentPolicyVersion.version.desc())).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent policy not found")
    return definition, policy


def list_agent_definitions(session: Session, principal: CurrentPrincipal) -> list[AgentDefinitionRead]:
    require_permission(session, principal, "agents.view")
    rows = session.exec(select(AgentDefinition).where(
        AgentDefinition.organization_id == principal.organization_id,
        AgentDefinition.institution_id == principal.institution_id,
        AgentDefinition.status == "ENABLED",
    ).order_by(AgentDefinition.agent_key, AgentDefinition.version.desc())).all()
    seen: set[str] = set()
    result: list[AgentDefinitionRead] = []
    for row in rows:
        if row.agent_key in seen or row.agent_key not in AGENTS:
            continue
        seen.add(row.agent_key)
        result.append(AgentDefinitionRead(
            agent_key=row.agent_key, maximum_autonomy=row.max_autonomy_level,
            capability_keys=list(row.capability_keys_json), tool_keys=list(row.tool_keys_json),
        ))
    return result


def run_integration_run_advisor(session: Session, principal: CurrentPrincipal, *, integration_run_id: UUID) -> AgentRunRead:
    agent_key = "integration_run_advisor"
    definition, policy = _definition_and_policy(session, principal, agent_key)
    context = build_context_envelope(session, principal, agent_key=agent_key, run_id=integration_run_id)
    request_material = {"agent_key": agent_key, "request_type": context.request_type, "integration_run_id": str(integration_run_id)}
    request_sha = _sha(request_material)
    existing = session.exec(select(AgentRun).where(
        AgentRun.institution_id == principal.institution_id, AgentRun.agent_key == agent_key,
        AgentRun.request_sha256 == request_sha,
    )).first()
    if existing is not None:
        return get_agent_run(session, principal, existing.id)
    run = AgentRun(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        actor_user_id=principal.user_id, agent_key=agent_key, agent_definition_id=definition.id,
        agent_definition_version=definition.version, policy_id=policy.id, policy_version=policy.version,
        request_type=context.request_type, request_sha256=request_sha, correlation_id=context.correlation_id,
    )
    session.add(run)
    session.flush()
    _append_event(session, principal, run, "CREATED", {"request_type": context.request_type})
    session.add(AgentRunStep(organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id, sequence=1, step_type="PLANNER", status="COMPLETED", summary_json={"planner": "DETERMINISTIC"}))
    plan = plan_integration_run_advisor(integration_run_id)
    if tuple(step.step_type for step in plan) != ("PLANNER", "POLICY", "EXECUTOR", "VERIFIER"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Planner produced forbidden steps")
    tool = known_tool("m24.integration_run.inspect")
    decision = evaluate_l0_policy(session, principal, known_agent(agent_key), tool,
                                  policy_max_autonomy=policy.max_autonomy_level,
                                  max_steps=policy.max_steps, max_tool_calls=policy.max_tool_calls)
    if not decision.allowed:
        _append_event(session, principal, run, "FAILED", {"code": decision.code})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent policy denied")
    session.add(AgentRunStep(organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id, sequence=2, step_type="POLICY", status="ALLOWED", summary_json={"code": decision.code}))
    _append_event(session, principal, run, "POLICY_ALLOWED", {"autonomy": "L0", "tool_key": tool.key})
    try:
        output = execute_inspection_tool(session, principal, run_id=integration_run_id)
        output_payload = output.model_dump(mode="json")
        session.add(AgentRunStep(organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id, sequence=3, step_type="EXECUTOR", status="COMPLETED", summary_json={"tool_key": tool.key}))
        session.add(AgentEvidenceRef(
            organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id,
            reference_key=output.evidence_refs[0].reference_key, source_module=output.evidence_refs[0].source_module,
            source_entity_type=output.evidence_refs[0].source_entity_type, source_entity_id=output.evidence_refs[0].source_entity_id,
            provenance_sha256=output.evidence_refs[0].provenance_sha256,
        ))
        verify_integration_run_advisor_output(output)
        session.add(AgentToolCall(
            organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id,
            sequence=1, tool_key=tool.key, schema_version=tool.input_schema_version,
            input_sha256=_sha({"run_id": str(integration_run_id)}), output_sha256=_sha(output_payload),
            verification_status="VERIFIED", safe_summary_json={"status": output.status, "counts": output.counts.model_dump()},
        ))
        session.add(AgentRunStep(organization_id=principal.organization_id, institution_id=principal.institution_id, run_id=run.id, sequence=4, step_type="VERIFIER", status="VERIFIED", summary_json={"evidence_refs": len(output.evidence_refs)}))
        _append_event(session, principal, run, "COMPLETED", {"output": output_payload})
        record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                     action="AGENT_RUN_COMPLETED", entity_type="AgentRun", entity_id=run.id,
                     metadata={"agent_key": agent_key, "correlation_id": str(run.correlation_id)})
        enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="agent.run.completed",
                                event_version=1, aggregate_type="agent_run", aggregate_id=run.id,
                                actor_user_id=principal.user_id, correlation_id=run.correlation_id,
                                payload={"agent_key": agent_key, "status": "COMPLETED"})
    except HTTPException:
        _append_event(session, principal, run, "FAILED", {"code": "VERIFICATION_OR_TOOL_FAILURE"})
        enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="agent.run.failed",
                                event_version=1, aggregate_type="agent_run", aggregate_id=run.id,
                                actor_user_id=principal.user_id, correlation_id=run.correlation_id,
                                payload={"agent_key": agent_key, "status": "FAILED"})
        record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                     action="AGENT_RUN_FAILED", entity_type="AgentRun", entity_id=run.id,
                     metadata={"agent_key": agent_key, "correlation_id": str(run.correlation_id)})
        session.flush()
        return get_agent_run(session, principal, run.id)
    session.flush()
    return get_agent_run(session, principal, run.id)


def _latest_event(session: Session, run_id: UUID) -> AgentRunEvent | None:
    return session.exec(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.sequence.desc())).first()


def get_agent_run(session: Session, principal: CurrentPrincipal, run_id: UUID) -> AgentRunRead:
    require_permission(session, principal, "agents.view")
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    latest = _latest_event(session, run.id)
    output = None
    if latest is not None and latest.event_type == "COMPLETED":
        output = IntegrationRunAdvisorOutput.model_validate(latest.metadata_json.get("output"))
    return AgentRunRead(id=run.id, agent_key=run.agent_key, request_type=run.request_type,
                        status=latest.event_type if latest is not None else "CREATED",
                        correlation_id=run.correlation_id, created_at=run.created_at, output=output)


def list_agent_runs(session: Session, principal: CurrentPrincipal, *, limit: int = 100) -> list[AgentRunRead]:
    require_permission(session, principal, "agents.view")
    rows = session.exec(select(AgentRun).where(
        AgentRun.organization_id == principal.organization_id, AgentRun.institution_id == principal.institution_id,
    ).order_by(AgentRun.created_at.desc()).limit(limit)).all()
    return [get_agent_run(session, principal, row.id) for row in rows]


def list_agent_steps(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentRunStepRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [AgentRunStepRead(sequence=row.sequence, step_type=row.step_type, status=row.status, created_at=row.created_at)
            for row in session.exec(select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.sequence).limit(100)).all()]


def list_agent_evidence(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentEvidenceRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [AgentEvidenceRead(reference_key=row.reference_key, source_module=row.source_module,
                              source_entity_type=row.source_entity_type, source_entity_id=row.source_entity_id,
                              provenance_sha256=row.provenance_sha256)
            for row in session.exec(select(AgentEvidenceRef).where(AgentEvidenceRef.run_id == run_id).order_by(AgentEvidenceRef.created_at).limit(100)).all()]


def list_agent_tool_calls(session: Session, principal: CurrentPrincipal, run_id: UUID) -> list[AgentToolCallRead]:
    get_agent_run(session, principal, run_id)
    require_permission(session, principal, "agents.audit.read")
    return [AgentToolCallRead(sequence=row.sequence, tool_key=row.tool_key, schema_version=row.schema_version,
                              verification_status=row.verification_status, created_at=row.created_at)
            for row in session.exec(select(AgentToolCall).where(AgentToolCall.run_id == run_id).order_by(AgentToolCall.sequence).limit(100)).all()]
