from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.accountability.ledger_service import _hash, _require
from app.modules.accountability.models import (
    AccountabilityCase,
    AccountabilityDecision,
    AccountabilityObligation,
)
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event

OBLIGATION_TYPES = frozenset({"INFORMATION_REQUIRED", "REVIEW_REQUIRED", "FOLLOW_UP_REQUIRED"})
LIFECYCLE_STATES = frozenset({"OPEN", "IN_PROGRESS", "COMPLETED", "WAIVED", "EXPIRED", "CANCELLED"})
EVIDENCE_TYPES = frozenset({"M21_FOLLOW_UP", "M21_ACTION", "M27_HUMAN_REVIEW", "M27_INFORMATION"})
NEXT_REQUIRED_STEPS = frozenset({"HUMAN_REVIEW_REQUIRED", "PROVIDE_INFORMATION", "COMPLETE_FOLLOW_UP"})
SLA_POLICY_KEY = "accountability.sla"
_MAX_SLA_SECONDS = 31_536_000


@dataclass(frozen=True, slots=True)
class ObligationResult:
    obligation: AccountabilityObligation
    created: bool


@dataclass(frozen=True, slots=True)
class SLAResolution:
    status: str
    due_at: datetime | None
    policy_key: str | None
    policy_version: int | None
    rule_code: str | None
    resolution_sha256: str


@dataclass(frozen=True, slots=True)
class ComplianceResult:
    status: str
    evaluated_at: datetime
    due_at: datetime | None
    lifecycle: str


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tenant_case(session: Session, principal: CurrentPrincipal, case_id: UUID, *, lock: bool = False) -> AccountabilityCase:
    statement = select(AccountabilityCase).where(
        AccountabilityCase.id == case_id,
        AccountabilityCase.organization_id == principal.organization_id,
        AccountabilityCase.institution_id == principal.institution_id,
    )
    if lock:
        statement = statement.with_for_update()
    case = session.exec(statement).one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accountability case not found")
    return case


def _validate_owner(session: Session, principal: CurrentPrincipal, owner_id: UUID | None) -> None:
    if owner_id is None:
        return
    found = session.exec(
        text(
            """
            SELECT 1 FROM memberships
            WHERE user_id = CAST(:user_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            LIMIT 1
            """
        ),
        params={
            "user_id": str(owner_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation owner not found in scope")


def _policy_rule_matches(rule: dict[str, Any], *, obligation_type: str, normalized_category: str | None, priority: str | None) -> bool:
    allowed = {"obligation_type", "normalized_category", "priority", "duration_seconds", "rule_code"}
    if set(rule) - allowed:
        return False
    if rule.get("obligation_type") != obligation_type:
        return False
    return all(
        rule.get(key) in (None, value)
        for key, value in (("normalized_category", normalized_category), ("priority", priority))
    )


def resolve_obligation_sla(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    obligation_type: str,
    created_at: datetime,
    normalized_category: str | None = None,
    priority: str | None = None,
) -> SLAResolution:
    if obligation_type not in OBLIGATION_TYPES:
        raise ValueError("unsupported obligation type")
    row = session.exec(
        text(
            """
            SELECT enabled, policy_json, policy_version
            FROM education_os_m27_read_effective_policy(
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :policy_key
            )
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "policy_key": SLA_POLICY_KEY,
        },
    ).first()
    if row is None or not bool(row[0]) or not isinstance(row[1], dict):
        reason = {"status": "NOT_EVALUABLE", "reason": "missing_or_disabled_policy", "policy_key": SLA_POLICY_KEY}
        return SLAResolution("NOT_EVALUABLE", None, None, None, None, _canonical_hash(reason))

    document = dict(row[1])
    rules = document.get("rules")
    if not isinstance(rules, list):
        reason = {"status": "NOT_EVALUABLE", "reason": "invalid_rules_document", "policy_key": SLA_POLICY_KEY, "policy_version": int(row[2])}
        return SLAResolution("NOT_EVALUABLE", None, SLA_POLICY_KEY, int(row[2]), None, _canonical_hash(reason))

    matches: list[tuple[int, int, dict[str, Any]]] = []
    for index, candidate in enumerate(rules):
        if not isinstance(candidate, dict) or not _policy_rule_matches(candidate, obligation_type=obligation_type, normalized_category=normalized_category, priority=priority):
            continue
        specificity = sum(candidate.get(key) is not None for key in ("normalized_category", "priority"))
        matches.append((specificity, index, candidate))
    if not matches:
        reason = {"status": "NOT_EVALUABLE", "reason": "no_matching_rule", "policy_key": SLA_POLICY_KEY, "policy_version": int(row[2]), "obligation_type": obligation_type}
        return SLAResolution("NOT_EVALUABLE", None, SLA_POLICY_KEY, int(row[2]), None, _canonical_hash(reason))

    best_specificity = max(item[0] for item in matches)
    best = [item for item in matches if item[0] == best_specificity]
    if len(best) != 1:
        reason = {"status": "NOT_EVALUABLE", "reason": "ambiguous_matching_rules", "policy_key": SLA_POLICY_KEY, "policy_version": int(row[2]), "obligation_type": obligation_type, "specificity": best_specificity}
        return SLAResolution("NOT_EVALUABLE", None, SLA_POLICY_KEY, int(row[2]), None, _canonical_hash(reason))

    _, index, rule = best[0]
    duration = rule.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 0 < duration <= _MAX_SLA_SECONDS:
        reason = {"status": "NOT_EVALUABLE", "reason": "invalid_duration", "policy_key": SLA_POLICY_KEY, "policy_version": int(row[2]), "rule_index": index}
        return SLAResolution("NOT_EVALUABLE", None, SLA_POLICY_KEY, int(row[2]), None, _canonical_hash(reason))
    rule_code = str(rule.get("rule_code") or f"{SLA_POLICY_KEY}:v{int(row[2])}:r{index}")
    due_at = created_at + timedelta(seconds=duration)
    resolution = {
        "status": "RESOLVED",
        "policy_key": SLA_POLICY_KEY,
        "policy_version": int(row[2]),
        "rule_code": rule_code,
        "duration_seconds": duration,
        "obligation_type": obligation_type,
        "normalized_category": normalized_category,
        "priority": priority,
        "created_at": created_at.isoformat(),
        "due_at": due_at.isoformat(),
    }
    return SLAResolution("RESOLVED", due_at, SLA_POLICY_KEY, int(row[2]), rule_code, _canonical_hash(resolution))


def _identity_hash(
    *,
    institution_id: UUID,
    case_id: UUID,
    origin_type: str,
    origin_id: UUID,
    obligation_type: str,
    predecessor_obligation_id: UUID | None,
) -> str:
    return _canonical_hash({
        "identity_version": 1,
        "institution_id": str(institution_id),
        "case_id": str(case_id),
        "origin_type": origin_type,
        "origin_id": str(origin_id),
        "obligation_type": obligation_type,
        "predecessor_obligation_id": str(predecessor_obligation_id) if predecessor_obligation_id else None,
    })


def create_accountability_obligation(
    session: Session,
    principal: CurrentPrincipal,
    case_id: UUID,
    *,
    origin_type: str,
    origin_id: UUID,
    obligation_type: str,
    creation_idempotency_key: str,
    provenance_sha256: str,
    normalized_category: str | None = None,
    priority: str | None = None,
    owner_user_id: UUID | None = None,
    predecessor_obligation_id: UUID | None = None,
    created_at: datetime | None = None,
) -> ObligationResult:
    _require(session, principal, "accountability.obligation.create")
    if origin_type not in {"DECISION", "REVIEW", "CASE"}:
        raise ValueError("unsupported obligation origin")
    if obligation_type not in OBLIGATION_TYPES:
        raise ValueError("unsupported obligation type")
    _hash(creation_idempotency_key, "creation_idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    case = _tenant_case(session, principal, case_id, lock=True)
    existing = session.exec(
        select(AccountabilityObligation).where(
            AccountabilityObligation.institution_id == principal.institution_id,
            AccountabilityObligation.identity_version == 1,
            AccountabilityObligation.identity_key_sha256 == _identity_hash(
                institution_id=principal.institution_id,
                case_id=case_id,
                origin_type=origin_type,
                origin_id=origin_id,
                obligation_type=obligation_type,
                predecessor_obligation_id=predecessor_obligation_id,
            ),
        )
    ).first()
    if existing is not None:
        return ObligationResult(existing, False)
    existing = session.exec(
        select(AccountabilityObligation).where(
            AccountabilityObligation.institution_id == principal.institution_id,
            AccountabilityObligation.creation_idempotency_key == creation_idempotency_key,
        )
    ).first()
    if existing is not None:
        return ObligationResult(existing, False)
    if owner_user_id is None:
        owner_user_id = case.primary_owner_user_id
    _validate_owner(session, principal, owner_user_id)
    if predecessor_obligation_id is not None:
        predecessor = session.exec(
            select(AccountabilityObligation).where(
                AccountabilityObligation.id == predecessor_obligation_id,
                AccountabilityObligation.organization_id == principal.organization_id,
                AccountabilityObligation.institution_id == principal.institution_id,
                AccountabilityObligation.case_id == case_id,
            )
        ).one_or_none()
        if predecessor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Predecessor obligation not found")
    timestamp = created_at or datetime.now(UTC)
    sla = resolve_obligation_sla(
        session,
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        obligation_type=obligation_type,
        created_at=timestamp,
        normalized_category=normalized_category or case.normalized_category,
        priority=priority,
    )
    obligation = AccountabilityObligation(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        case_id=case_id,
        origin_type=origin_type,
        origin_id=origin_id,
        obligation_type=obligation_type,
        next_required_step="HUMAN_REVIEW_REQUIRED",
        identity_key_sha256=_identity_hash(
            institution_id=principal.institution_id,
            case_id=case_id,
            origin_type=origin_type,
            origin_id=origin_id,
            obligation_type=obligation_type,
            predecessor_obligation_id=predecessor_obligation_id,
        ),
        owner_user_id=owner_user_id,
        created_at=timestamp,
        due_at=sla.due_at,
        sla_status=sla.status,
        sla_policy_key=sla.policy_key,
        sla_policy_version=sla.policy_version,
        sla_rule_code=sla.rule_code,
        sla_resolution_sha256=sla.resolution_sha256,
        provenance_sha256=provenance_sha256,
        creation_idempotency_key=creation_idempotency_key,
        predecessor_obligation_id=predecessor_obligation_id,
        created_by_user_id=principal.user_id,
    )
    session.add(obligation)
    session.flush()
    canonical = enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="accountability.obligation.created",
        event_version=1,
        aggregate_type="accountability_obligation",
        aggregate_id=obligation.id,
        actor_user_id=principal.user_id,
        payload={"case_id": str(case_id), "obligation_id": str(obligation.id), "obligation_type": obligation_type, "origin_type": origin_type, "origin_id": str(origin_id), "owner_user_id": str(owner_user_id) if owner_user_id else None},
        metadata={"provenance_sha256": provenance_sha256, "sla_status": sla.status, "sla_policy_key": sla.policy_key, "sla_policy_version": sla.policy_version},
    )
    session.flush()
    obligation.canonical_event_id = canonical.id
    session.add(obligation)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.obligation.created", entity_type="AccountabilityObligation", entity_id=obligation.id, metadata={"case_id": str(case_id), "obligation_type": obligation_type, "sla_status": sla.status, "provenance_sha256": provenance_sha256})
    return ObligationResult(obligation, True)


def materialize_obligation_from_decision(session: Session, principal: CurrentPrincipal, decision_id: UUID, *, provenance_sha256: str) -> ObligationResult:
    decision = session.exec(
        select(AccountabilityDecision).where(
            AccountabilityDecision.id == decision_id,
            AccountabilityDecision.organization_id == principal.organization_id,
            AccountabilityDecision.institution_id == principal.institution_id,
        )
    ).one_or_none()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    if decision.decision_type != "REQUEST_INFORMATION":
        raise ValueError("only REQUEST_INFORMATION materializes an information obligation")
    return create_accountability_obligation(
        session,
        principal,
        decision.case_id,
        origin_type="DECISION",
        origin_id=decision.id,
        obligation_type="INFORMATION_REQUIRED",
        creation_idempotency_key=_canonical_hash({"decision_id": str(decision.id), "obligation_type": "INFORMATION_REQUIRED"}),
        provenance_sha256=provenance_sha256,
    )


def _locked_obligation(session: Session, principal: CurrentPrincipal, obligation_id: UUID) -> AccountabilityObligation:
    obligation = session.exec(
        select(AccountabilityObligation).where(
            AccountabilityObligation.id == obligation_id,
            AccountabilityObligation.organization_id == principal.organization_id,
            AccountabilityObligation.institution_id == principal.institution_id,
        ).with_for_update()
    ).one_or_none()
    if obligation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accountability obligation not found")
    return obligation


def _validate_evidence(session: Session, principal: CurrentPrincipal, obligation: AccountabilityObligation, evidence_type: str, evidence_id: UUID) -> None:
    if evidence_type not in EVIDENCE_TYPES:
        raise ValueError("unsupported completion evidence type")
    queries = {
        "M21_FOLLOW_UP": "SELECT 1 FROM intervention_followups WHERE id = CAST(:evidence_id AS uuid) AND organization_id = CAST(:organization_id AS uuid) AND institution_id = CAST(:institution_id AS uuid)",
        "M21_ACTION": "SELECT 1 FROM intervention_actions WHERE id = CAST(:evidence_id AS uuid) AND organization_id = CAST(:organization_id AS uuid) AND institution_id = CAST(:institution_id AS uuid)",
        "M27_HUMAN_REVIEW": "SELECT 1 FROM accountability_reviews WHERE id = CAST(:evidence_id AS uuid) AND organization_id = CAST(:organization_id AS uuid) AND institution_id = CAST(:institution_id AS uuid) AND case_id = CAST(:case_id AS uuid)",
        "M27_INFORMATION": "SELECT 1 FROM event_ledger WHERE id = CAST(:evidence_id AS uuid) AND organization_id = CAST(:organization_id AS uuid) AND institution_id = CAST(:institution_id AS uuid)",
    }
    found = session.exec(
        text(queries[evidence_type]),
        params={"evidence_id": str(evidence_id), "organization_id": str(principal.organization_id), "institution_id": str(principal.institution_id), "case_id": str(obligation.case_id)},
    ).first()
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Completion evidence is not available in tenant scope")


def complete_accountability_obligation(session: Session, principal: CurrentPrincipal, obligation_id: UUID, *, evidence_type: str, evidence_id: UUID, evidence_fingerprint_sha256: str, idempotency_key: str, provenance_sha256: str, completed_at: datetime | None = None) -> ObligationResult:
    _require(session, principal, "accountability.obligation.complete")
    _hash(evidence_fingerprint_sha256, "evidence_fingerprint_sha256")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    obligation = _locked_obligation(session, principal, obligation_id)
    if obligation.completion_idempotency_key == idempotency_key:
        return ObligationResult(obligation, False)
    if obligation.lifecycle != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only open obligations can be completed")
    _validate_evidence(session, principal, obligation, evidence_type, evidence_id)
    timestamp = completed_at or datetime.now(UTC)
    obligation.lifecycle = "COMPLETED"
    obligation.completed_at = timestamp
    obligation.completed_by_user_id = principal.user_id
    obligation.completion_evidence_type = evidence_type
    obligation.completion_evidence_id = evidence_id
    obligation.completion_evidence_fingerprint_sha256 = evidence_fingerprint_sha256
    obligation.completion_idempotency_key = idempotency_key
    obligation.projection_version += 1
    canonical = enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="accountability.obligation.completed", event_version=1, aggregate_type="accountability_obligation", aggregate_id=obligation.id, actor_user_id=principal.user_id, payload={"case_id": str(obligation.case_id), "obligation_id": str(obligation.id), "evidence_type": evidence_type, "evidence_id": str(evidence_id), "completed_at": timestamp.isoformat()}, metadata={"provenance_sha256": provenance_sha256})
    session.flush()
    session.add(obligation)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.obligation.completed", entity_type="AccountabilityObligation", entity_id=obligation.id, metadata={"evidence_type": evidence_type, "evidence_id": str(evidence_id), "canonical_event_id": str(canonical.id), "provenance_sha256": provenance_sha256})
    return ObligationResult(obligation, True)


def waive_accountability_obligation(session: Session, principal: CurrentPrincipal, obligation_id: UUID, *, reason_code: str, evidence_id: UUID | None, idempotency_key: str, provenance_sha256: str, waived_at: datetime | None = None) -> ObligationResult:
    _require(session, principal, "accountability.obligation.waive")
    if not reason_code or len(reason_code.strip()) < 3:
        raise ValueError("waiver reason code is required")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    obligation = _locked_obligation(session, principal, obligation_id)
    if obligation.waiver_idempotency_key == idempotency_key:
        return ObligationResult(obligation, False)
    if obligation.lifecycle != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only open obligations can be waived")
    timestamp = waived_at or datetime.now(UTC)
    obligation.lifecycle = "WAIVED"
    obligation.waived_at = timestamp
    obligation.waived_by_user_id = principal.user_id
    obligation.waiver_reason_code = reason_code.strip()
    obligation.waiver_evidence_id = evidence_id
    obligation.waiver_idempotency_key = idempotency_key
    obligation.projection_version += 1
    canonical = enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="accountability.obligation.waived", event_version=1, aggregate_type="accountability_obligation", aggregate_id=obligation.id, actor_user_id=principal.user_id, payload={"case_id": str(obligation.case_id), "obligation_id": str(obligation.id), "reason_code": obligation.waiver_reason_code, "evidence_id": str(evidence_id) if evidence_id else None, "waived_at": timestamp.isoformat()}, metadata={"provenance_sha256": provenance_sha256})
    session.flush()
    session.add(obligation)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.obligation.waived", entity_type="AccountabilityObligation", entity_id=obligation.id, metadata={"reason_code": obligation.waiver_reason_code, "canonical_event_id": str(canonical.id), "provenance_sha256": provenance_sha256})
    return ObligationResult(obligation, True)


def transfer_obligation_owner(session: Session, principal: CurrentPrincipal, obligation_id: UUID, owner_user_id: UUID | None, *, idempotency_key: str, provenance_sha256: str, reason_reference: str | None = None) -> ObligationResult:
    _require(session, principal, "accountability.obligation.ownership.manage")
    _hash(idempotency_key, "idempotency_key")
    _hash(provenance_sha256, "provenance_sha256")
    obligation = _locked_obligation(session, principal, obligation_id)
    existing = session.exec(
        select(AccountabilityObligation).where(
            AccountabilityObligation.institution_id == principal.institution_id,
            AccountabilityObligation.owner_transfer_idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None:
        return ObligationResult(existing, False)
    if obligation.lifecycle != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only open obligations can transfer ownership")
    if obligation.owner_user_id == owner_user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Obligation already has that owner")
    _validate_owner(session, principal, owner_user_id)
    previous = obligation.owner_user_id
    obligation.owner_user_id = owner_user_id
    obligation.owner_transfer_idempotency_key = idempotency_key
    obligation.projection_version += 1
    canonical = enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="accountability.obligation.owner.transferred", event_version=1, aggregate_type="accountability_obligation", aggregate_id=obligation.id, actor_user_id=principal.user_id, payload={"case_id": str(obligation.case_id), "obligation_id": str(obligation.id), "previous_owner_user_id": str(previous) if previous else None, "new_owner_user_id": str(owner_user_id) if owner_user_id else None, "reason_reference": reason_reference, "idempotency_key": idempotency_key}, metadata={"provenance_sha256": provenance_sha256})
    session.flush()
    session.add(obligation)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id, action="accountability.obligation.owner.transferred", entity_type="AccountabilityObligation", entity_id=obligation.id, metadata={"previous_owner_user_id": str(previous) if previous else None, "new_owner_user_id": str(owner_user_id) if owner_user_id else None, "canonical_event_id": str(canonical.id), "provenance_sha256": provenance_sha256})
    return ObligationResult(obligation, True)


def evaluate_obligation_compliance(obligation: AccountabilityObligation, *, now: datetime | None = None) -> ComplianceResult:
    evaluated_at = now or datetime.now(UTC)
    if obligation.lifecycle == "WAIVED":
        return ComplianceResult("EXEMPT", evaluated_at, obligation.due_at, obligation.lifecycle)
    if obligation.lifecycle == "EXPIRED":
        return ComplianceResult("NON_COMPLIANT", evaluated_at, obligation.due_at, obligation.lifecycle)
    if obligation.lifecycle == "CANCELLED":
        return ComplianceResult("NOT_EVALUABLE", evaluated_at, obligation.due_at, obligation.lifecycle)
    if obligation.due_at is None or obligation.sla_status != "RESOLVED":
        return ComplianceResult("NOT_EVALUABLE", evaluated_at, obligation.due_at, obligation.lifecycle)
    if obligation.lifecycle == "COMPLETED":
        return ComplianceResult("COMPLIANT" if obligation.completed_at is not None and obligation.completed_at <= obligation.due_at else "NON_COMPLIANT", evaluated_at, obligation.due_at, obligation.lifecycle)
    return ComplianceResult("PENDING" if evaluated_at <= obligation.due_at else "NON_COMPLIANT", evaluated_at, obligation.due_at, obligation.lifecycle)


def is_obligation_overdue(obligation: AccountabilityObligation, *, now: datetime | None = None) -> bool:
    evaluated_at = now or datetime.now(UTC)
    return obligation.lifecycle == "OPEN" and obligation.due_at is not None and obligation.sla_status == "RESOLVED" and evaluated_at > obligation.due_at
