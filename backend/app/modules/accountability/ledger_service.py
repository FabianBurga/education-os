from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.accountability.models import (
    AccountabilityCase,
    AccountabilityDecision,
    AccountabilityOwnershipEvent,
    AccountabilityReview,
)
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event
from app.modules.m21_access import has_permission

REVIEW_DISPOSITIONS = frozenset({
    "CONFIRMED",
    "NEEDS_INFORMATION",
    "CONTINUE_MONITORING",
    "READY_FOR_DECISION",
    "NO_CURRENT_CONCERN",
})
DECISION_TYPES = frozenset({
    "NO_ACTION_REQUIRED",
    "MONITOR",
    "REQUEST_INFORMATION",
    "CREATE_INTERVENTION",
    "CONTINUE_INTERVENTION",
    "ESCALATE",
    "CLOSE_CASE",
})
EXECUTION_REQUIRED_DECISIONS = frozenset({
    "REQUEST_INFORMATION",
    "CREATE_INTERVENTION",
    "CONTINUE_INTERVENTION",
    "ESCALATE",
})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class LedgerResult:
    record: object
    created: bool


def _hash(value: str, label: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a SHA-256 hex digest")


def _require(session: Session, principal: CurrentPrincipal, permission: str) -> None:
    if not has_permission(session, principal, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permission: {permission}")


def _permission_context(session: Session, principal: CurrentPrincipal) -> dict[str, object]:
    permission_rows = session.exec(
        text(
            """
            SELECT p.key
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id = m.id
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE m.user_id = CAST(:user_id AS uuid)
              AND m.institution_id = CAST(:institution_id AS uuid)
              AND m.status = 'ACTIVE'
            ORDER BY p.key
            """
        ),
        params={"user_id": str(principal.user_id), "institution_id": str(principal.institution_id)},
    ).all()
    return {
        "principal_user_id": str(principal.user_id),
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "effective_permissions": [str(row[0]) for row in permission_rows],
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _case_for_update(session: Session, principal: CurrentPrincipal, case_id: UUID) -> AccountabilityCase:
    case = session.exec(
        select(AccountabilityCase)
        .where(
            AccountabilityCase.id == case_id,
            AccountabilityCase.organization_id == principal.organization_id,
            AccountabilityCase.institution_id == principal.institution_id,
        )
        .with_for_update()
    ).one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accountability case not found")
    return case


def _validate_owner(session: Session, principal: CurrentPrincipal, owner_id: UUID) -> None:
    exists = session.exec(
        text(
            """
            SELECT 1 FROM memberships
            WHERE user_id = CAST(:user_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            LIMIT 1
            """
        ),
        params={"user_id": str(owner_id), "institution_id": str(principal.institution_id)},
    ).first()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accountable owner not found in scope")


def _ownership(
    session: Session,
    principal: CurrentPrincipal,
    case_id: UUID,
    *,
    event_type: str,
    new_owner_user_id: UUID | None,
    idempotency_key: str,
    provenance_sha256: str,
    reason_reference: str | None,
) -> LedgerResult:
    _require(session, principal, "accountability.ownership.manage")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    case = _case_for_update(session, principal, case_id)
    existing = session.exec(
        select(AccountabilityOwnershipEvent).where(
            AccountabilityOwnershipEvent.institution_id == principal.institution_id,
            AccountabilityOwnershipEvent.case_id == case_id,
            AccountabilityOwnershipEvent.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return LedgerResult(existing, False)
    previous = case.primary_owner_user_id
    if event_type == "ASSIGNED" and previous is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case already has an accountable owner")
    if event_type == "TRANSFERRED" and (previous is None or previous == new_owner_user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case is not transferable to that owner")
    if event_type == "UNASSIGNED" and previous is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case is already unassigned")
    if new_owner_user_id is not None:
        _validate_owner(session, principal, new_owner_user_id)
    context = _permission_context(session, principal)
    event = AccountabilityOwnershipEvent(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        case_id=case_id,
        event_type=event_type,
        previous_owner_user_id=previous,
        new_owner_user_id=new_owner_user_id,
        changed_by_user_id=principal.user_id,
        changed_at=datetime.now(UTC),
        reason_reference=reason_reference,
        effective_permission_context_json=context,
        idempotency_key=idempotency_key,
        provenance_sha256=provenance_sha256,
    )
    session.add(event)
    session.flush()
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=f"accountability.owner.{event_type.lower()}",
        event_version=1,
        aggregate_type="accountability_case",
        aggregate_id=case_id,
        actor_user_id=principal.user_id,
        payload={"case_id": str(case_id), "ownership_event_id": str(event.id), "event_type": event_type},
        metadata={"provenance_sha256": provenance_sha256},
    )
    session.flush()
    case.primary_owner_user_id = new_owner_user_id
    case.owner_state = "ASSIGNED" if new_owner_user_id is not None else "UNASSIGNED"
    case.projection_version += 1
    case.updated_at = datetime.now(UTC)
    session.add(case)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action=f"accountability.owner.{event_type.lower()}", entity_type="AccountabilityCase", entity_id=case_id, metadata={"ownership_event_id": str(event.id), "provenance_sha256": provenance_sha256})
    return LedgerResult(event, True)


def assign_case_owner(session: Session, principal: CurrentPrincipal, case_id: UUID, owner_id: UUID, *, idempotency_key: str, provenance_sha256: str, reason_reference: str | None = None) -> LedgerResult:
    return _ownership(session, principal, case_id, event_type="ASSIGNED", new_owner_user_id=owner_id, idempotency_key=idempotency_key, provenance_sha256=provenance_sha256, reason_reference=reason_reference)


def transfer_case_owner(session: Session, principal: CurrentPrincipal, case_id: UUID, owner_id: UUID, *, idempotency_key: str, provenance_sha256: str, reason_reference: str | None = None) -> LedgerResult:
    return _ownership(session, principal, case_id, event_type="TRANSFERRED", new_owner_user_id=owner_id, idempotency_key=idempotency_key, provenance_sha256=provenance_sha256, reason_reference=reason_reference)


def unassign_case_owner(session: Session, principal: CurrentPrincipal, case_id: UUID, *, idempotency_key: str, provenance_sha256: str, reason_reference: str | None = None) -> LedgerResult:
    return _ownership(session, principal, case_id, event_type="UNASSIGNED", new_owner_user_id=None, idempotency_key=idempotency_key, provenance_sha256=provenance_sha256, reason_reference=reason_reference)


def record_case_review(session: Session, principal: CurrentPrincipal, case_id: UUID, *, disposition: str, evidence_refs: list[str], evidence_fingerprint_sha256: str, next_required_step: str, idempotency_key: str, provenance_sha256: str, reviewed_at: datetime | None = None, note_reference: str | None = None, policy_key: str | None = None, policy_version: int | None = None) -> LedgerResult:
    _require(session, principal, "accountability.review")
    if disposition not in REVIEW_DISPOSITIONS:
        raise ValueError("unsupported review disposition")
    if not evidence_refs:
        raise ValueError("review evidence references are required")
    _hash(evidence_fingerprint_sha256, "evidence_fingerprint_sha256")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    _case_for_update(session, principal, case_id)
    existing = session.exec(select(AccountabilityReview).where(AccountabilityReview.institution_id == principal.institution_id, AccountabilityReview.case_id == case_id, AccountabilityReview.idempotency_key == idempotency_key)).first()
    if existing is not None:
        return LedgerResult(existing, False)
    context = _permission_context(session, principal)
    review = AccountabilityReview(organization_id=principal.organization_id, institution_id=principal.institution_id, case_id=case_id, reviewer_user_id=principal.user_id, effective_permission_context_json=context, reviewed_at=reviewed_at or datetime.now(UTC), disposition=disposition, evidence_refs_json=evidence_refs, evidence_fingerprint_sha256=evidence_fingerprint_sha256, policy_key=policy_key, policy_version=policy_version, note_reference=note_reference, next_required_step=next_required_step, idempotency_key=idempotency_key, provenance_sha256=provenance_sha256)
    session.add(review)
    session.flush()
    enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="accountability.review.completed", event_version=1, aggregate_type="accountability_case", aggregate_id=case_id, actor_user_id=principal.user_id, payload={"case_id": str(case_id), "review_id": str(review.id), "disposition": disposition, "evidence_fingerprint_sha256": evidence_fingerprint_sha256}, metadata={"provenance_sha256": provenance_sha256})
    session.flush()
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.review.completed", entity_type="AccountabilityCase", entity_id=case_id, metadata={"review_id": str(review.id), "disposition": disposition, "provenance_sha256": provenance_sha256})
    return LedgerResult(review, True)


def record_case_decision(session: Session, principal: CurrentPrincipal, case_id: UUID, *, review_id: UUID, decision_type: str, evidence_refs: list[str], evidence_fingerprint_sha256: str, idempotency_key: str, provenance_sha256: str, reason_reference: str | None = None, policy_key: str | None = None, policy_version: int | None = None, recorded_at: datetime | None = None) -> LedgerResult:
    _require(session, principal, "accountability.decide")
    if decision_type not in DECISION_TYPES:
        raise ValueError("unsupported decision type")
    if not evidence_refs:
        raise ValueError("decision evidence references are required")
    _hash(evidence_fingerprint_sha256, "evidence_fingerprint_sha256")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    _case_for_update(session, principal, case_id)
    review = session.exec(select(AccountabilityReview).where(AccountabilityReview.id == review_id, AccountabilityReview.organization_id == principal.organization_id, AccountabilityReview.institution_id == principal.institution_id, AccountabilityReview.case_id == case_id)).one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Decision requires a review for the same case")
    existing = session.exec(select(AccountabilityDecision).where(AccountabilityDecision.institution_id == principal.institution_id, AccountabilityDecision.case_id == case_id, AccountabilityDecision.idempotency_key == idempotency_key)).first()
    if existing is not None:
        return LedgerResult(existing, False)
    context = _permission_context(session, principal)
    decision = AccountabilityDecision(organization_id=principal.organization_id, institution_id=principal.institution_id, case_id=case_id, decision_actor_user_id=principal.user_id, review_id=review_id, effective_permission_context_json=context, recorded_at=recorded_at or datetime.now(UTC), decision_type=decision_type, evidence_refs_json=evidence_refs, evidence_fingerprint_sha256=evidence_fingerprint_sha256, policy_key=policy_key, policy_version=policy_version, reason_reference=reason_reference, execution_required=decision_type in EXECUTION_REQUIRED_DECISIONS, idempotency_key=idempotency_key, provenance_sha256=provenance_sha256)
    session.add(decision)
    session.flush()
    enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="accountability.decision.recorded", event_version=1, aggregate_type="accountability_case", aggregate_id=case_id, actor_user_id=principal.user_id, payload={"case_id": str(case_id), "decision_id": str(decision.id), "review_id": str(review_id), "decision_type": decision_type, "execution_required": decision.execution_required, "evidence_fingerprint_sha256": evidence_fingerprint_sha256}, metadata={"provenance_sha256": provenance_sha256})
    session.flush()
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.decision.recorded", entity_type="AccountabilityCase", entity_id=case_id, metadata={"decision_id": str(decision.id), "decision_type": decision_type, "provenance_sha256": provenance_sha256})
    if decision_type == "REQUEST_INFORMATION":
        from app.modules.accountability.obligation_service import (
            materialize_obligation_from_decision,
        )

        materialize_obligation_from_decision(session, principal, decision.id, provenance_sha256=provenance_sha256)
    return LedgerResult(decision, True)
