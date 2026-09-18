from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.agents.registry import known_tool
from app.modules.agents.schemas import (
    AgentCountsRead,
    AgentEvidenceRead,
    AgentIssueRead,
    AgentProvenanceRead,
    FollowupSummaryRead,
    InstitutionIntelligenceAdvisorOutput,
    IntegrationRunAdvisorOutput,
    IntelligenceProvenanceRead,
    IntelligenceSignalSummaryRead,
    InterventionSummaryRead,
    StudentTimelineAdvisorOutput,
    StudentTimelineSummaryRead,
)
from app.modules.integrations.service import get_run, list_run_events, list_run_items
from app.modules.intelligence.decision_surfaces import (
    inspect_current_institution_intelligence,
)
from app.modules.m21_access import has_permission
from app.modules.student_timeline.service import list_student_timeline

ERROR_EXPLANATIONS = {
    "ACADEMIC_PERIOD_NOT_FOUND": "The academic period could not be resolved.",
    "EXTERNAL_ID_DUPLICATE": "The external student identifier is duplicated in this import.",
    "ALREADY_APPLIED": "This external student identifier was already applied by this connector.",
    "STUDENT_IDENTITY_CONFLICT": "The student identity conflicts with an existing record.",
    "SECTION_NOT_FOUND": "The target section could not be resolved.",
    "DOMAIN_COMMAND_FAILED": "The governed domain command did not complete.",
}


def _safe_explanation(code: str) -> str:
    return ERROR_EXPLANATIONS.get(code, "The row requires manual review using its stable error code.")


def inspect_integration_run(
    session: Session, principal: CurrentPrincipal, *, run_id: UUID,
) -> IntegrationRunAdvisorOutput:
    tool = known_tool("m24.integration_run.inspect")
    if tool.side_effect_class != "NONE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Side-effecting tools are prohibited")
    run = get_run(session, principal, run_id)
    items = list_run_items(session, principal, run_id)
    issues = [
        AgentIssueRead(
            row_number=item.source_row_number, code=item.error_code or "UNKNOWN",
            category=item.status, safe_explanation=_safe_explanation(item.error_code or "UNKNOWN"),
        )
        for item in items if item.error_code
    ]
    event_count = 0
    if has_permission(session, principal, "integrations.audit.read"):
        event_count = len(list_run_events(session, principal, run_id))
    evidence = AgentEvidenceRead(
        reference_key=f"m24:integration_run:{run.id}", source_module="integrations",
        source_entity_type="IntegrationRun", source_entity_id=run.id,
        provenance_sha256=run.source_fingerprint_sha256,
    )
    counts = AgentCountsRead(
        total=run.total_rows, valid=run.valid_rows, invalid=run.invalid_rows,
        conflicts=run.conflict_rows, applied=run.applied_rows, failed=run.failed_rows,
    )
    summary = (
        f"Integration run {run.status}: {counts.total} rows, {counts.valid} valid, "
        f"{counts.invalid} invalid, {counts.conflicts} conflicts, {counts.applied} applied, "
        f"and {counts.failed} failed."
    )
    if event_count:
        summary += f" {event_count} authorized lifecycle events were verified."
    safe_next_action = (
        "Review the stable error codes and immutable provenance in Integration Hub; "
        "any apply action remains a separate human-controlled operation."
    )
    return IntegrationRunAdvisorOutput(
        run_id=run.id, status=run.status, summary=summary, counts=counts, issues=issues,
        provenance=AgentProvenanceRead(
            connector_key=run.connector_key, sanitized_filename=run.source_filename,
            source_sha256=run.source_fingerprint_sha256,
        ), safe_next_action=safe_next_action, evidence_refs=[evidence],
    )


def _evidence_hash(value: object) -> str:
    return sha256(repr(value).encode("utf-8")).hexdigest()


def _intervention_states(entries) -> InterventionSummaryRead:
    latest_states: dict[UUID, str] = {}
    for entry in entries:
        if entry.category != "INTERVENTION":
            continue
        value = entry.context_json.get("status")
        if not isinstance(value, str):
            value = entry.context_json.get("to_status")
        if isinstance(value, str) and value in {"OPEN", "IN_PROGRESS", "CLOSED"}:
            latest_states.setdefault(entry.source_aggregate_id, value)
        else:
            latest_states.setdefault(entry.source_aggregate_id, "UNKNOWN")
    states = list(latest_states.values())
    return InterventionSummaryRead(
        total=len(latest_states), open=states.count("OPEN"),
        in_progress=states.count("IN_PROGRESS"), closed=states.count("CLOSED"),
    )


def inspect_student_timeline(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_id: UUID,
) -> StudentTimelineAdvisorOutput:
    tool = known_tool("m21.student_timeline.inspect")
    if tool.side_effect_class != "NONE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Side-effecting tools are prohibited")
    page = list_student_timeline(
        session, principal, student_profile_id=student_id, limit=100,
    )
    entries = page.entries
    event_types = sorted({entry.event_type for entry in entries})[:20]
    followups = [entry for entry in entries if entry.category == "FOLLOW_UP"]
    evidence = [
        AgentEvidenceRead(
            reference_key=f"m21:student-timeline-scope:{student_id}",
            source_module="student_timeline",
            source_entity_type="StudentProfile",
            source_entity_id=student_id,
            provenance_sha256=_evidence_hash((str(student_id), "authorized_timeline_scope")),
        ),
        *[
        AgentEvidenceRead(
            reference_key=f"m21:timeline-entry:{entry.id}",
            source_module="student_timeline",
            source_entity_type="StudentTimelineEntry",
            source_entity_id=entry.id,
            provenance_sha256=_evidence_hash((
                str(entry.id), str(entry.student_profile_id), entry.ledger_position,
                entry.event_type, entry.category, entry.sensitivity,
                entry.occurred_at.isoformat(),
            )),
        )
        for entry in entries[:25]
        ],
    ]
    latest_event_at = max((entry.occurred_at for entry in entries), default=None)
    latest_followup = max((entry.occurred_at for entry in followups), default=None)
    timeline = StudentTimelineSummaryRead(
        event_count=len(entries), recent_event_types=event_types,
        latest_event_at=latest_event_at,
    )
    interventions = _intervention_states(entries)
    followup_summary = FollowupSummaryRead(total=len(followups), latest_at=latest_followup)
    return StudentTimelineAdvisorOutput(
        student_id=student_id,
        summary=(
            f"Authorized timeline contains {timeline.event_count} events and "
            f"{interventions.total} intervention references."
        ),
        timeline=timeline, interventions=interventions, followups=followup_summary,
        issues=[],
        safe_next_action=(
            "Review the authorized Student Timeline entries and use the existing "
            "human-controlled intervention workflow for any follow-up."
        ),
        evidence_refs=evidence,
    )


def _freshness(snapshot_date: date) -> str:
    age_days = max(0, (datetime.now(UTC).date() - snapshot_date).days)
    return "CURRENT" if age_days == 0 else f"STALE_{age_days}_DAYS"


def inspect_institution_intelligence(
    session: Session,
    principal: CurrentPrincipal,
) -> InstitutionIntelligenceAdvisorOutput:
    tool = known_tool("m22.intelligence_snapshot.inspect")
    if tool.side_effect_class != "NONE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Side-effecting tools are prohibited")
    snapshot = inspect_current_institution_intelligence(session, principal)
    signals = IntelligenceSignalSummaryRead(
        total=snapshot.open_signal_total, low=snapshot.open_signal_low,
        medium=snapshot.open_signal_medium, high=snapshot.open_signal_high,
    )
    evidence = AgentEvidenceRead(
        reference_key=f"m22:institution-snapshot:{snapshot.snapshot_id}",
        source_module="intelligence",
        source_entity_type="InstitutionIntelligenceDaily",
        source_entity_id=snapshot.snapshot_id,
        provenance_sha256=_evidence_hash((
            str(snapshot.snapshot_id), snapshot.snapshot_date.isoformat(),
            snapshot.policy_key, snapshot.policy_version, snapshot.rule_set_version,
            snapshot.projection_version,
        )),
    )
    return InstitutionIntelligenceAdvisorOutput(
        snapshot_id=snapshot.snapshot_id, snapshot_date=snapshot.snapshot_date,
        freshness=_freshness(snapshot.snapshot_date),
        summary=(
            f"Current institutional snapshot has {signals.total} open signals: "
            f"{signals.high} high, {signals.medium} medium, and {signals.low} low."
        ),
        signals=signals, top_categories=snapshot.top_signal_categories,
        provenance=IntelligenceProvenanceRead(
            policy_key=snapshot.policy_key, policy_version=snapshot.policy_version,
            generated_at=snapshot.generated_at,
        ),
        safe_next_action=(
            "Review the authorized institutional intelligence evidence and use "
            "existing human-governed workflows for any intervention decision."
        ),
        evidence_refs=[evidence],
    )


def canonical_hash(value: object) -> str:
    return sha256(str(value).encode("utf-8")).hexdigest()
