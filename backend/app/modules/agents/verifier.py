from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.schemas import (
    AgentAdvisorOutput,
    InstitutionIntelligenceAdvisorOutput,
    IntegrationRunAdvisorOutput,
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
