from __future__ import annotations

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
    IntegrationRunAdvisorOutput,
)
from app.modules.integrations.service import get_run, list_run_events, list_run_items
from app.modules.m21_access import has_permission

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


def canonical_hash(value: object) -> str:
    return sha256(str(value).encode("utf-8")).hexdigest()
