from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.accountability.ledger_service import _require

QUEUE_REASONS = frozenset({
    "UNASSIGNED",
    "REVIEW_REQUIRED",
    "DECISION_REQUIRED",
    "INFORMATION_REQUIRED",
    "FOLLOW_UP_REQUIRED",
    "OBLIGATION_DUE",
    "OBLIGATION_OVERDUE",
})
QUEUE_NEXT_STEPS = frozenset({
    "ASSIGN_OWNER",
    "HUMAN_REVIEW",
    "RECORD_DECISION",
    "PROVIDE_INFORMATION",
    "COMPLETE_FOLLOW_UP",
    "WAIT_FOR_DUE_DATE",
    "NO_IMMEDIATE_ACTION",
})
PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}
_CURSOR_VERSION = 1
_MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class AccountabilityQueueItem:
    case_id: UUID
    identity_version: int
    identity_key_sha256: str
    source_category: str
    normalized_category: str
    attention_reasons: tuple[str, ...]
    owner_state: str
    owner_user_id: UUID | None
    review_required: bool
    decision_required: bool
    open_obligation_id: UUID | None
    open_obligation_type: str | None
    next_required_step: str
    due_at: datetime | None
    sla_status: str
    compliance_status: str
    m22_priority: str | None
    m22_snapshot_id: UUID | None
    case_age_seconds: int
    generated_at: datetime
    source_freshness: datetime | None
    projection_version: int
    policy_versions: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    _sort_key: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class AccountabilityQueuePage:
    items: tuple[AccountabilityQueueItem, ...]
    next_cursor: str | None
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class AccountabilityCaseDetail:
    item: AccountabilityQueueItem
    source_lineage: tuple[dict[str, Any], ...]
    ownership_history: tuple[dict[str, Any], ...]
    reviews: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    obligations: tuple[dict[str, Any], ...]
    m21_links: tuple[dict[str, Any], ...]
    m22_reference: dict[str, Any] | None
    generated_at: datetime


def _bounded_limit(value: int) -> int:
    return max(1, min(int(value), _MAX_LIMIT))


def _cursor_encode(principal: CurrentPrincipal, sort_key: tuple[Any, ...]) -> str:
    payload = {
        "version": _CURSOR_VERSION,
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "sort": [item.isoformat() if isinstance(item, datetime) else (str(item) if isinstance(item, UUID) else item) for item in sort_key],
    }
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def _cursor_decode(principal: CurrentPrincipal, cursor: str | None) -> tuple[int, int, datetime, datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if payload.get("version") != _CURSOR_VERSION or payload.get("organization_id") != str(principal.organization_id) or payload.get("institution_id") != str(principal.institution_id):
            raise ValueError
        sort = payload["sort"]
        if len(sort) != 5:
            raise ValueError
        return int(sort[0]), int(sort[1]), datetime.fromisoformat(sort[2]), datetime.fromisoformat(sort[3]), UUID(str(sort[4]))
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or foreign accountability queue cursor") from exc


def _reasons(row: Any, now: datetime) -> tuple[str, ...]:
    reasons: list[str] = []
    if row.owner_user_id is None:
        reasons.append("UNASSIGNED")
    if bool(row.review_required):
        reasons.append("REVIEW_REQUIRED")
    if bool(row.decision_required):
        reasons.append("DECISION_REQUIRED")
    if row.open_obligation_type == "INFORMATION_REQUIRED":
        reasons.append("INFORMATION_REQUIRED")
    elif row.open_obligation_type == "FOLLOW_UP_REQUIRED":
        reasons.append("FOLLOW_UP_REQUIRED")
    if row.due_at is not None and row.compliance_status == "NON_COMPLIANT":
        reasons.append("OBLIGATION_OVERDUE")
    elif row.due_at is not None and row.open_obligation_id is not None and row.compliance_status == "PENDING":
        reasons.append("OBLIGATION_DUE")
    return tuple(reasons)


def _next_step(row: Any) -> str:
    if row.owner_user_id is None:
        return "ASSIGN_OWNER"
    if row.open_obligation_type == "INFORMATION_REQUIRED":
        return "PROVIDE_INFORMATION"
    if row.open_obligation_type == "FOLLOW_UP_REQUIRED":
        return "COMPLETE_FOLLOW_UP"
    if row.open_obligation_type == "REVIEW_REQUIRED":
        return "HUMAN_REVIEW"
    if bool(row.review_required):
        return "HUMAN_REVIEW"
    if bool(row.decision_required):
        return "RECORD_DECISION"
    if row.due_at is not None and row.compliance_status == "PENDING":
        return "WAIT_FOR_DUE_DATE"
    return "NO_IMMEDIATE_ACTION"


def _row_to_item(row: Any, *, generated_at: datetime, now: datetime) -> AccountabilityQueueItem:
    reasons = _reasons(row, now)
    policy_versions = tuple(
        value
        for value in (
            f"{row.sla_policy_key}:v{row.sla_policy_version}" if row.sla_policy_key and row.sla_policy_version else None,
            f"{row.m22_policy_key}:v{row.m22_policy_version}" if row.m22_policy_key and row.m22_policy_version else None,
        )
        if value
    )
    provenance = tuple(
        value
        for value in (
            f"case:{row.identity_key_sha256}",
            f"obligation:{row.obligation_provenance_sha256}" if row.obligation_provenance_sha256 else None,
            f"m22:{row.m22_snapshot_id}" if row.m22_snapshot_id else None,
        )
        if value
    )
    return AccountabilityQueueItem(
        case_id=row.case_id,
        identity_version=int(row.identity_version),
        identity_key_sha256=str(row.identity_key_sha256),
        source_category=str(row.source_category),
        normalized_category=str(row.normalized_category),
        attention_reasons=reasons,
        owner_state=str(row.owner_state),
        owner_user_id=row.owner_user_id,
        review_required=bool(row.review_required),
        decision_required=bool(row.decision_required),
        open_obligation_id=row.open_obligation_id,
        open_obligation_type=(str(row.open_obligation_type) if row.open_obligation_type else None),
        next_required_step=_next_step(row),
        due_at=row.due_at,
        sla_status=str(row.sla_status or "NOT_EVALUABLE"),
        compliance_status=str(row.compliance_status),
        m22_priority=(str(row.m22_priority) if row.m22_priority else None),
        m22_snapshot_id=row.m22_snapshot_id,
        case_age_seconds=max(0, int((now - row.created_at).total_seconds())),
        generated_at=generated_at,
        source_freshness=row.source_freshness,
        projection_version=max(int(row.projection_version), int(row.obligation_projection_version or 1)),
        policy_versions=policy_versions,
        provenance_refs=provenance,
        _sort_key=(int(row.attention_rank), int(row.priority_rank), row.due_sort, row.created_at, row.case_id),
    )


def _queue_rows(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owner_user_id: UUID | None,
    unassigned: bool,
    reason: str | None,
    lifecycle: str | None,
    normalized_category: str | None,
    priority: str | None,
    obligation_type: str | None,
    compliance_status: str | None,
    due_window_hours: int | None,
    review_required: bool | None,
    decision_required: bool | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[Any], datetime]:
    now = datetime.now(UTC)
    cursor_values = _cursor_decode(principal, cursor)
    params: dict[str, Any] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "owner_user_id": str(owner_user_id) if owner_user_id else None,
        "normalized_category": normalized_category,
        "priority": priority,
        "obligation_type": obligation_type,
        "compliance_status": compliance_status,
        "lifecycle": lifecycle,
        "due_window_end": now + timedelta(hours=due_window_hours) if due_window_hours is not None else None,
        "review_required": review_required,
        "decision_required": decision_required,
        "limit": _bounded_limit(limit) + 1,
        "cursor_attention": cursor_values[0] if cursor_values else None,
        "cursor_priority": cursor_values[1] if cursor_values else None,
        "cursor_due": cursor_values[2] if cursor_values else None,
        "cursor_created": cursor_values[3] if cursor_values else None,
        "cursor_case_id": str(cursor_values[4]) if cursor_values else None,
    }
    reason_clauses = {
        "UNASSIGNED": "owner_user_id IS NULL",
        "REVIEW_REQUIRED": "review_required",
        "DECISION_REQUIRED": "decision_required",
        "INFORMATION_REQUIRED": "open_obligation_type = 'INFORMATION_REQUIRED'",
        "FOLLOW_UP_REQUIRED": "open_obligation_type = 'FOLLOW_UP_REQUIRED'",
        "OBLIGATION_DUE": "open_obligation_id IS NOT NULL AND compliance_status = 'PENDING'",
        "OBLIGATION_OVERDUE": "open_obligation_id IS NOT NULL AND compliance_status = 'NON_COMPLIANT'",
    }
    params["now"] = now
    where = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
        "attention_rank < 6",
        "(CAST(:owner_user_id AS uuid) IS NULL OR owner_user_id = CAST(:owner_user_id AS uuid))",
        "(CAST(:normalized_category AS text) IS NULL OR normalized_category = CAST(:normalized_category AS text))",
        "(CAST(:priority AS text) IS NULL OR m22_priority = CAST(:priority AS text))",
        "(CAST(:obligation_type AS text) IS NULL OR open_obligation_type = CAST(:obligation_type AS text))",
        "(CAST(:compliance_status AS text) IS NULL OR compliance_status = CAST(:compliance_status AS text))",
        "(CAST(:lifecycle AS text) IS NULL OR lifecycle = CAST(:lifecycle AS text))",
        "(CAST(:due_window_end AS timestamptz) IS NULL OR (due_at IS NOT NULL AND due_at <= CAST(:due_window_end AS timestamptz)))",
        "(CAST(:review_required AS boolean) IS NULL OR review_required = CAST(:review_required AS boolean))",
        "(CAST(:decision_required AS boolean) IS NULL OR decision_required = CAST(:decision_required AS boolean))",
        "(CAST(:cursor_attention AS integer) IS NULL OR (attention_rank, priority_rank, due_sort, created_at, case_id) > (CAST(:cursor_attention AS integer), CAST(:cursor_priority AS integer), CAST(:cursor_due AS timestamptz), CAST(:cursor_created AS timestamptz), CAST(:cursor_case_id AS uuid)))",
    ]
    if unassigned:
        where.append("owner_user_id IS NULL")
    if reason is not None:
        if reason not in QUEUE_REASONS:
            raise ValueError("unsupported queue attention reason")
        where.append(reason_clauses[reason])
    query = text(
        f"""
        WITH base AS (
            SELECT
                c.id AS case_id,
                c.organization_id,
                c.institution_id,
                c.identity_version,
                c.identity_key_sha256,
                c.source_category,
                c.normalized_category,
                c.owner_state,
                c.primary_owner_user_id AS owner_user_id,
                c.lifecycle,
                c.created_at,
                c.projection_version,
                latest_review.id AS latest_review_id,
                latest_review.disposition AS latest_review_disposition,
                latest_review.reviewed_at AS latest_reviewed_at,
                latest_decision.id AS latest_decision_id,
                latest_decision.recorded_at AS latest_decision_at,
                obligation.id AS open_obligation_id,
                obligation.obligation_type AS open_obligation_type,
                obligation.due_at,
                obligation.sla_status,
                obligation.lifecycle AS obligation_lifecycle,
                obligation.completed_at,
                obligation.projection_version AS obligation_projection_version,
                obligation.sla_policy_key,
                obligation.sla_policy_version,
                obligation.provenance_sha256 AS obligation_provenance_sha256,
                m22.id AS m22_snapshot_id,
                m22.overall_priority AS m22_priority,
                m22.evaluated_at AS source_freshness,
                m22.policy_key AS m22_policy_key,
                m22.policy_version AS m22_policy_version
            FROM accountability_cases c
            LEFT JOIN LATERAL (
                SELECT r.id, r.disposition, r.reviewed_at
                FROM accountability_reviews r
                WHERE r.case_id = c.id
                  AND r.organization_id = c.organization_id
                  AND r.institution_id = c.institution_id
                ORDER BY r.reviewed_at DESC, r.id DESC
                LIMIT 1
            ) latest_review ON true
            LEFT JOIN LATERAL (
                SELECT d.id, d.recorded_at
                FROM accountability_decisions d
                WHERE d.case_id = c.id
                  AND d.organization_id = c.organization_id
                  AND d.institution_id = c.institution_id
                ORDER BY d.recorded_at DESC, d.id DESC
                LIMIT 1
            ) latest_decision ON true
            LEFT JOIN LATERAL (
                SELECT o.id, o.obligation_type, o.due_at, o.sla_status,
                       o.lifecycle, o.completed_at, o.projection_version,
                       o.sla_policy_key, o.sla_policy_version, o.provenance_sha256
                FROM accountability_obligations o
                WHERE o.case_id = c.id
                  AND o.organization_id = c.organization_id
                  AND o.institution_id = c.institution_id
                  AND o.lifecycle IN ('OPEN','IN_PROGRESS')
                ORDER BY
                    CASE WHEN o.due_at IS NOT NULL AND o.due_at < :now THEN 0 ELSE 1 END,
                    o.due_at NULLS LAST,
                    o.created_at,
                    o.id
                LIMIT 1
            ) obligation ON true
            LEFT JOIN LATERAL (
                SELECT s.id, s.overall_priority, s.evaluated_at, s.policy_key, s.policy_version
                FROM student_intelligence_snapshots s
                WHERE c.subject_type = 'STUDENT'
                  AND s.student_profile_id = c.subject_id
                  AND s.organization_id = c.organization_id
                  AND s.institution_id = c.institution_id
                ORDER BY s.snapshot_date DESC, s.evaluated_at DESC, s.id DESC
                LIMIT 1
            ) m22 ON true
            WHERE c.organization_id = CAST(:organization_id AS uuid)
              AND c.institution_id = CAST(:institution_id AS uuid)
              AND c.lifecycle IN ('OPEN','REOPENED')
        ), derived AS (
            SELECT *,
                (latest_review_id IS NULL) AS review_required,
                (latest_review_id IS NOT NULL AND (latest_decision_id IS NULL OR latest_decision_at < latest_reviewed_at)) AS decision_required,
                CASE
                    WHEN obligation_lifecycle = 'WAIVED' THEN 'EXEMPT'
                    WHEN due_at IS NULL OR sla_status <> 'RESOLVED' THEN 'NOT_EVALUABLE'
                    WHEN obligation_lifecycle = 'COMPLETED' AND completed_at IS NOT NULL AND completed_at <= due_at THEN 'COMPLIANT'
                    WHEN obligation_lifecycle = 'COMPLETED' THEN 'NON_COMPLIANT'
                    WHEN :now <= due_at THEN 'PENDING'
                    ELSE 'NON_COMPLIANT'
                END AS compliance_status,
                CASE
                    WHEN obligation_lifecycle IN ('OPEN','IN_PROGRESS') AND due_at IS NOT NULL AND due_at < :now THEN 0
                    WHEN obligation_lifecycle IN ('OPEN','IN_PROGRESS') AND due_at IS NOT NULL THEN 1
                    WHEN owner_user_id IS NULL THEN 2
                    WHEN latest_review_id IS NULL THEN 3
                    WHEN latest_decision_id IS NULL OR latest_decision_at < latest_reviewed_at THEN 4
                    WHEN m22_priority = 'HIGH' THEN 5
                    ELSE 6
                END AS attention_rank,
                CASE m22_priority WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END AS priority_rank,
                COALESCE(due_at, TIMESTAMPTZ '9999-12-31 23:59:59+00') AS due_sort
            FROM base
        )
        SELECT * FROM derived
        WHERE {' AND '.join(where)}
        ORDER BY attention_rank, priority_rank, due_sort, created_at, case_id
        LIMIT :limit
        """
    )
    rows = session.exec(query, params=params).all()
    return rows, now


def list_accountability_queue(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owner_user_id: UUID | None = None,
    unassigned: bool = False,
    reason: str | None = None,
    lifecycle: str | None = None,
    normalized_category: str | None = None,
    priority: str | None = None,
    obligation_type: str | None = None,
    compliance_status: str | None = None,
    due_window_hours: int | None = None,
    review_required: bool | None = None,
    decision_required: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AccountabilityQueuePage:
    _require(session, principal, "accountability.view")
    if priority is not None and priority not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("unsupported queue priority")
    if compliance_status is not None and compliance_status not in {"PENDING", "COMPLIANT", "NON_COMPLIANT", "EXEMPT", "NOT_EVALUABLE"}:
        raise ValueError("unsupported queue compliance status")
    if due_window_hours is not None and not 0 <= due_window_hours <= 24 * 365:
        raise ValueError("due_window_hours is outside the supported range")
    rows, now = _queue_rows(
        session,
        principal,
        owner_user_id=owner_user_id,
        unassigned=unassigned,
        reason=reason,
        lifecycle=lifecycle,
        normalized_category=normalized_category,
        priority=priority,
        obligation_type=obligation_type,
        compliance_status=compliance_status,
        due_window_hours=due_window_hours,
        review_required=review_required,
        decision_required=decision_required,
        cursor=cursor,
        limit=limit,
    )
    generated_at = datetime.now(UTC)
    bounded = _bounded_limit(limit)
    has_more = len(rows) > bounded
    items = tuple(_row_to_item(row, generated_at=generated_at, now=now) for row in rows[:bounded])
    next_cursor = _cursor_encode(principal, items[-1]._sort_key) if has_more and items else None
    return AccountabilityQueuePage(items=items, next_cursor=next_cursor, generated_at=generated_at)


def get_accountability_queue_item(session: Session, principal: CurrentPrincipal, case_id: UUID) -> AccountabilityQueueItem:
    _require(session, principal, "accountability.view")
    rows, now = _queue_rows(
        session,
        principal,
        owner_user_id=None,
        unassigned=False,
        reason=None,
        lifecycle=None,
        normalized_category=None,
        priority=None,
        obligation_type=None,
        compliance_status=None,
        due_window_hours=None,
        review_required=None,
        decision_required=None,
        cursor=None,
        limit=_MAX_LIMIT,
    )
    for row in rows:
        if row.case_id == case_id:
            return _row_to_item(row, generated_at=datetime.now(UTC), now=now)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accountability queue item not found")


def get_accountability_case_detail(session: Session, principal: CurrentPrincipal, case_id: UUID) -> AccountabilityCaseDetail:
    item = get_accountability_queue_item(session, principal, case_id)
    params = {"organization_id": str(principal.organization_id), "institution_id": str(principal.institution_id), "case_id": str(case_id)}
    source_rows = session.exec(text("SELECT source_kind, source_entity_id, source_event_id, source_category, source_provenance_sha256, source_fingerprint_sha256, observed_at FROM accountability_case_sources WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND case_id=CAST(:case_id AS uuid) ORDER BY observed_at, id"), params=params).all()
    owner_rows = session.exec(text("SELECT event_type, previous_owner_user_id, new_owner_user_id, changed_by_user_id, changed_at, reason_reference, provenance_sha256 FROM accountability_ownership_events WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND case_id=CAST(:case_id AS uuid) ORDER BY changed_at, id"), params=params).all()
    review_rows = session.exec(text("SELECT id, reviewer_user_id, reviewed_at, disposition, evidence_refs_json, evidence_fingerprint_sha256, next_required_step, policy_key, policy_version, provenance_sha256 FROM accountability_reviews WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND case_id=CAST(:case_id AS uuid) ORDER BY reviewed_at DESC, id DESC"), params=params).all()
    decision_rows = session.exec(text("SELECT id, decision_actor_user_id, recorded_at, decision_type, review_id, evidence_refs_json, evidence_fingerprint_sha256, policy_key, policy_version, execution_required, provenance_sha256 FROM accountability_decisions WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND case_id=CAST(:case_id AS uuid) ORDER BY recorded_at DESC, id DESC"), params=params).all()
    obligation_rows = session.exec(text("SELECT id, origin_type, origin_id, obligation_type, owner_user_id, created_at, due_at, lifecycle, sla_status, sla_policy_key, sla_policy_version, completed_at, completion_evidence_type, completion_evidence_id, waived_at, waiver_reason_code, predecessor_obligation_id, provenance_sha256 FROM accountability_obligations WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND case_id=CAST(:case_id AS uuid) ORDER BY created_at DESC, id DESC"), params=params).all()
    m22_reference = ({"snapshot_id": str(item.m22_snapshot_id), "priority": item.m22_priority, "source_freshness": item.source_freshness.isoformat() if item.source_freshness else None} if item.m22_snapshot_id else None)
    return AccountabilityCaseDetail(
        item=item,
        source_lineage=tuple({"source_kind": row[0], "source_entity_id": str(row[1]), "source_event_id": str(row[2]) if row[2] else None, "source_category": row[3], "source_provenance_sha256": row[4], "source_fingerprint_sha256": row[5], "observed_at": row[6]} for row in source_rows),
        ownership_history=tuple({"event_type": row[0], "previous_owner_user_id": str(row[1]) if row[1] else None, "new_owner_user_id": str(row[2]) if row[2] else None, "changed_by_user_id": str(row[3]), "changed_at": row[4], "reason_reference": row[5], "provenance_sha256": row[6]} for row in owner_rows),
        reviews=tuple({"review_id": str(row[0]), "reviewer_user_id": str(row[1]), "reviewed_at": row[2], "disposition": row[3], "evidence_refs": row[4], "evidence_fingerprint_sha256": row[5], "next_required_step": row[6], "policy_key": row[7], "policy_version": row[8], "provenance_sha256": row[9]} for row in review_rows),
        decisions=tuple({"decision_id": str(row[0]), "decision_actor_user_id": str(row[1]), "recorded_at": row[2], "decision_type": row[3], "review_id": str(row[4]), "evidence_refs": row[5], "evidence_fingerprint_sha256": row[6], "policy_key": row[7], "policy_version": row[8], "execution_required": row[9], "provenance_sha256": row[10]} for row in decision_rows),
        obligations=tuple({"obligation_id": str(row[0]), "origin_type": row[1], "origin_id": str(row[2]), "obligation_type": row[3], "owner_user_id": str(row[4]) if row[4] else None, "created_at": row[5], "due_at": row[6], "lifecycle": row[7], "sla_status": row[8], "sla_policy_key": row[9], "sla_policy_version": row[10], "completed_at": row[11], "completion_evidence_type": row[12], "completion_evidence_id": str(row[13]) if row[13] else None, "waived_at": row[14], "waiver_reason_code": row[15], "predecessor_obligation_id": str(row[16]) if row[16] else None, "provenance_sha256": row[17]} for row in obligation_rows),
        m21_links=tuple({"source_type": row[12], "source_id": str(row[13])} for row in obligation_rows if row[12] in {"M21_FOLLOW_UP", "M21_ACTION"} and row[13]),
        m22_reference=m22_reference,
        generated_at=datetime.now(UTC),
    )
