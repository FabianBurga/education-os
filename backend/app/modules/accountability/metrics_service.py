from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.accountability.ledger_service import _require
from app.modules.accountability.metrics_schemas import (
    MetricExplanation,
    MetricPopulation,
    MetricProvenance,
    MetricResult,
    MetricSummary,
    OutcomeSummary,
)

METRIC_VERSION = "m27-6.v1"
ADMIN_TIME_SAVED = "ADMINISTRATIVE_TIME_SAVED"
METRIC_IDS = (
    "TIME_TO_DETECTION",
    "TIME_TO_REVIEW",
    "TIME_TO_INTERVENTION",
    "FOLLOW_UP_COMPLIANCE",
    "LOST_CASE_RATE",
    "RECURRENCE_RATE",
    "INTERVENTION_OUTCOME",
    "REVIEW_ACCOUNTABILITY_RATE",
    "DECISION_ACCOUNTABILITY_RATE",
    "NEXT_ACTION_COMPLIANCE",
    ADMIN_TIME_SAVED,
)
_SOURCES = (
    "accountability_cases",
    "accountability_case_sources",
    "accountability_reviews",
    "accountability_decisions",
    "accountability_obligations",
    "interventions",
)
_OUTCOME_MAP = {
    "IMPROVED": "POSITIVE",
    "STABLE": "NO_CHANGE",
    "NO_CHANGE": "NO_CHANGE",
    "WORSENED": "WORSENED",
    "REFERRED": "UNRESOLVED",
    "TRANSFERRED": "UNRESOLVED",
    "NOT_ASSESSABLE": "INSUFFICIENT_EVIDENCE",
}
_DEFINITIONS = {
    "TIME_TO_DETECTION": (
        "How quickly was an actionable case registered?",
        "accepted source to opened case",
        "valid detection intervals",
        "eligible cases",
        "seconds",
    ),
    "TIME_TO_REVIEW": (
        "How quickly was required review completed?",
        "case opened to first valid human review",
        "valid review intervals",
        "review-required cases",
        "seconds",
    ),
    "TIME_TO_INTERVENTION": (
        "How quickly did accepted intent reach M21?",
        "CREATE_INTERVENTION decision to M21 accepted creation",
        "accepted creations",
        "eligible create decisions",
        "seconds",
    ),
    "FOLLOW_UP_COMPLIANCE": (
        "Were obligations completed on time?",
        "obligation due state and evidence",
        "on-time completions",
        "obligations due or terminal",
        "ratio",
    ),
    "LOST_CASE_RATE": (
        "What proportion became unaccounted for?",
        "opened case to observation cutoff",
        "lost eligible cases",
        "eligible cases with closed observation window",
        "ratio",
    ),
    "RECURRENCE_RATE": (
        "How often did resolved cases recur?",
        "resolved case to true new episode",
        "TRUE_RECURRENCE cases",
        "resolved cases with full policy window",
        "ratio",
    ),
    "INTERVENTION_OUTCOME": (
        "What was observed after intervention?",
        "M21 intervention to outcome window end",
        "interventions with observed outcome",
        "eligible interventions",
        "observations",
    ),
    "REVIEW_ACCOUNTABILITY_RATE": (
        "Were required reviews completed on time?",
        "review-required case to valid human review",
        "eligible cases with valid review",
        "review-required cases",
        "ratio",
    ),
    "DECISION_ACCOUNTABILITY_RATE": (
        "Were required decisions recorded on time?",
        "decision-required case to M27 decision",
        "eligible cases with valid decision",
        "decision-required cases",
        "ratio",
    ),
    "NEXT_ACTION_COMPLIANCE": (
        "Were required next steps completed or waived by due date?",
        "obligation creation to evidence",
        "on-time completion or authorized waiver",
        "obligations due",
        "ratio",
    ),
    ADMIN_TIME_SAVED: (
        "Did a validated workflow reduce human time?",
        "approved task baseline to measured completion",
        "not measured from logs",
        "approved baseline sample",
        "seconds",
    ),
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _policy(session: Session, principal: CurrentPrincipal) -> tuple[dict[str, Any], int] | None:
    row = session.exec(
        text(
            "SELECT enabled, policy_json, policy_version FROM education_os_m27_read_effective_policy(CAST(:organization_id AS uuid), CAST(:institution_id AS uuid), 'accountability.metrics')"
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if not row or not bool(row[0]) or not isinstance(row[1], dict):
        return None
    return dict(row[1]), int(row[2])


def _population(principal: CurrentPrincipal, cohort_id: UUID | None) -> MetricPopulation:
    if cohort_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unsupported or unauthorized cohort scope"
        )
    return MetricPopulation(institution_id=principal.institution_id)


def _explanation(metric_id: str, reason: str | None = None) -> MetricExplanation:
    q, definition, numerator, denominator, _ = _DEFINITIONS[metric_id]
    return MetricExplanation(
        business_question=q,
        definition=definition,
        numerator_definition=numerator,
        denominator_definition=denominator,
        exclusions=(
            "invalid provenance",
            "test data",
            "out-of-scope data",
            "incomplete policy window",
        ),
        status_reason=reason,
        metric_version=METRIC_VERSION,
    )


def get_metric_definition(metric_id: str) -> MetricExplanation:
    if metric_id not in METRIC_IDS:
        raise ValueError("unsupported accountability metric")
    return _explanation(metric_id)


def _result(
    metric_id: str,
    principal: CurrentPrincipal,
    start: datetime,
    end: datetime,
    *,
    metric_status: str,
    reason: str | None = None,
    policy_version: int | None = None,
    suppression_state: str = "NONE",
    numerator: float | int | None = None,
    denominator: int | None = None,
    value: float | None = None,
    unit: str | None = None,
    not_evaluable_count: int = 0,
    freshness: str = "UNKNOWN",
) -> MetricResult:
    population = MetricPopulation(institution_id=principal.institution_id)
    provenance = MetricProvenance(
        source_read_models=_SOURCES,
        lineage_digest=_digest(
            [metric_id, start, end, principal.organization_id, principal.institution_id]
        ),
        calculator=f"{metric_id}:{METRIC_VERSION}",
        exclusions=(
            "invalid provenance",
            "test data",
            "out-of-scope data",
            "incomplete policy window",
        ),
    )
    return MetricResult(
        metric_id=metric_id,
        metric_version=METRIC_VERSION,
        status=metric_status,
        value=value,
        unit=unit or _DEFINITIONS[metric_id][4],
        numerator=numerator,
        denominator=denominator,
        window_start=start,
        window_end=end,
        population=population,
        not_evaluable_count=not_evaluable_count,
        freshness=freshness,
        policy_version=policy_version,
        generated_at=datetime.now(UTC),
        provenance=provenance,
        suppression_state=suppression_state,
        reason=reason,
        explanation=_explanation(metric_id, reason),
    )


def _counts(
    session: Session, principal: CurrentPrincipal, metric_id: str, start: datetime, end: datetime
) -> tuple[int, int, int]:
    params = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "start": start,
        "end": end,
    }
    queries = {
        "TIME_TO_DETECTION": "SELECT AVG(EXTRACT(EPOCH FROM (c.created_at - s.observed_at))::double precision), count(*), count(*) FILTER (WHERE s.observed_at > c.created_at) FROM accountability_cases c JOIN accountability_case_sources s ON s.case_id=c.id AND s.organization_id=c.organization_id AND s.institution_id=c.institution_id WHERE c.organization_id=CAST(:organization_id AS uuid) AND c.institution_id=CAST(:institution_id AS uuid) AND c.created_at >= :start AND c.created_at < :end AND s.observed_at <= c.created_at",
        "TIME_TO_REVIEW": "SELECT AVG(EXTRACT(EPOCH FROM (r.reviewed_at - c.created_at))::double precision), count(*), count(*) FILTER (WHERE r.reviewed_at < c.created_at) FROM accountability_reviews r JOIN accountability_cases c ON c.id=r.case_id AND c.organization_id=r.organization_id AND c.institution_id=r.institution_id WHERE r.organization_id=CAST(:organization_id AS uuid) AND r.institution_id=CAST(:institution_id AS uuid) AND r.reviewed_at >= :start AND r.reviewed_at < :end AND r.reviewed_at >= c.created_at",
        "TIME_TO_INTERVENTION": "SELECT AVG(EXTRACT(EPOCH FROM (i.opened_at - d.recorded_at))::double precision), count(*), 0 FROM accountability_decisions d JOIN intervention_links l ON l.entity_id=d.id AND l.entity_type='ACCOUNTABILITY_DECISION' JOIN interventions i ON i.id=l.intervention_id AND i.organization_id=d.organization_id AND i.institution_id=d.institution_id WHERE d.organization_id=CAST(:organization_id AS uuid) AND d.institution_id=CAST(:institution_id AS uuid) AND d.decision_type='CREATE_INTERVENTION' AND d.recorded_at >= :start AND d.recorded_at < :end AND i.opened_at >= d.recorded_at",
        "REVIEW_ACCOUNTABILITY_RATE": "SELECT count(DISTINCT r.case_id), count(DISTINCT c.id), 0 FROM accountability_cases c LEFT JOIN accountability_reviews r ON r.case_id=c.id AND r.organization_id=c.organization_id AND r.institution_id=c.institution_id WHERE c.organization_id=CAST(:organization_id AS uuid) AND c.institution_id=CAST(:institution_id AS uuid) AND c.created_at >= :start AND c.created_at < :end AND c.lifecycle IN ('OPEN','REOPENED')",
        "DECISION_ACCOUNTABILITY_RATE": "SELECT count(DISTINCT d.case_id), count(DISTINCT c.id), 0 FROM accountability_cases c LEFT JOIN accountability_decisions d ON d.case_id=c.id AND d.organization_id=c.organization_id AND d.institution_id=c.institution_id WHERE c.organization_id=CAST(:organization_id AS uuid) AND c.institution_id=CAST(:institution_id AS uuid) AND c.created_at >= :start AND c.created_at < :end AND c.lifecycle IN ('OPEN','REOPENED')",
        "FOLLOW_UP_COMPLIANCE": "SELECT count(*) FILTER (WHERE o.lifecycle='COMPLETED' AND o.due_at IS NOT NULL AND o.completed_at <= o.due_at), count(*) FILTER (WHERE o.due_at IS NOT NULL), count(*) FILTER (WHERE o.due_at IS NULL OR o.sla_status <> 'RESOLVED') FROM accountability_obligations o WHERE o.organization_id=CAST(:organization_id AS uuid) AND o.institution_id=CAST(:institution_id AS uuid) AND o.created_at >= :start AND o.created_at < :end",
        "NEXT_ACTION_COMPLIANCE": "SELECT count(*) FILTER (WHERE (o.lifecycle='COMPLETED' AND o.completed_at <= o.due_at) OR o.lifecycle='WAIVED'), count(*) FILTER (WHERE o.due_at IS NOT NULL), count(*) FILTER (WHERE o.due_at IS NULL OR o.sla_status <> 'RESOLVED') FROM accountability_obligations o WHERE o.organization_id=CAST(:organization_id AS uuid) AND o.institution_id=CAST(:institution_id AS uuid) AND o.created_at >= :start AND o.created_at < :end",
        "LOST_CASE_RATE": "SELECT count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM accountability_reviews r WHERE r.case_id=c.id AND r.organization_id=c.organization_id AND r.institution_id=c.institution_id) AND NOT EXISTS (SELECT 1 FROM accountability_decisions d WHERE d.case_id=c.id AND d.organization_id=c.organization_id AND d.institution_id=c.institution_id) AND NOT EXISTS (SELECT 1 FROM accountability_obligations o WHERE o.case_id=c.id AND o.organization_id=c.organization_id AND o.institution_id=c.institution_id AND o.lifecycle IN ('OPEN','IN_PROGRESS','COMPLETED','WAIVED'))), count(*), 0 FROM accountability_cases c WHERE c.organization_id=CAST(:organization_id AS uuid) AND c.institution_id=CAST(:institution_id AS uuid) AND c.created_at >= :start AND c.created_at < :end AND c.lifecycle='RESOLVED'",
        "RECURRENCE_RATE": "SELECT count(*) FILTER (WHERE c.recurrence_classification='TRUE_RECURRENCE'), count(*), 0 FROM accountability_cases c WHERE c.organization_id=CAST(:organization_id AS uuid) AND c.institution_id=CAST(:institution_id AS uuid) AND c.created_at >= :start AND c.created_at < :end AND c.recurrence_classification IN ('TRUE_RECURRENCE','NEW_EPISODE')",
        "INTERVENTION_OUTCOME": "SELECT count(*) FILTER (WHERE i.outcome_type IS NOT NULL), count(*), count(*) FILTER (WHERE i.outcome_type IS NULL) FROM interventions i WHERE i.organization_id=CAST(:organization_id AS uuid) AND i.institution_id=CAST(:institution_id AS uuid) AND i.opened_at >= :start AND i.opened_at < :end",
    }
    query = queries.get(metric_id)
    if query is None:
        return 0, 0, 0
    row = session.exec(text(query), params=params).first()
    return (float(row[0] or 0), int(row[1] or 0), int(row[2] or 0)) if row else (0.0, 0, 0)


def get_accountability_metric(
    session: Session,
    principal: CurrentPrincipal,
    metric_id: str,
    *,
    start: datetime,
    end: datetime,
    cohort_id: UUID | None = None,
) -> MetricResult:
    _require(session, principal, "accountability.view")
    metric_id = metric_id.upper()
    if metric_id not in METRIC_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported accountability metric",
        )
    _population(principal, cohort_id)
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("window must be bounded UTC with end after start")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if metric_id == ADMIN_TIME_SAVED:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="NOT_COMPUTABLE",
            reason="BASELINE_REQUIRED",
            unit="seconds",
        )
    policy = _policy(session, principal)
    if policy is None:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="NOT_EVALUABLE",
            reason="METRIC_POLICY_REQUIRED",
            suppression_state="POLICY_MISSING",
        )
    document, policy_version = policy
    required_policy_key = {
        "LOST_CASE_RATE": "lost_case",
        "RECURRENCE_RATE": "recurrence_window_days",
    }.get(metric_id)
    if required_policy_key is not None and required_policy_key not in document:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="NOT_EVALUABLE",
            reason="REQUIRED_POLICY_RULE_MISSING",
            policy_version=policy_version,
        )
    threshold = document.get("small_cell_threshold")
    if not isinstance(threshold, int) or threshold < 1:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="SUPPRESSED",
            reason="SMALL_CELL_POLICY_REQUIRED",
            policy_version=policy_version,
            suppression_state="POLICY_MISSING",
        )
    numerator, denominator, not_evaluable = _counts(session, principal, metric_id, start, end)
    if denominator < threshold:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="SUPPRESSED",
            reason="SMALL_CELL_THRESHOLD",
            policy_version=policy_version,
            suppression_state="SMALL_CELL",
        )
    if denominator == 0:
        return _result(
            metric_id,
            principal,
            start,
            end,
            metric_status="NOT_COMPUTABLE",
            reason="EMPTY_POPULATION",
            policy_version=policy_version,
            not_evaluable_count=not_evaluable,
        )
    return _result(
        metric_id,
        principal,
        start,
        end,
        metric_status="COMPUTED",
        policy_version=policy_version,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        unit=_DEFINITIONS[metric_id][4],
        not_evaluable_count=not_evaluable,
        freshness="CURRENT",
    )


def get_accountability_metrics_summary(
    session: Session,
    principal: CurrentPrincipal,
    *,
    metric_ids: tuple[str, ...] | None,
    start: datetime,
    end: datetime,
    cohort_id: UUID | None = None,
) -> MetricSummary:
    ids = metric_ids or METRIC_IDS
    return MetricSummary(
        items=tuple(
            get_accountability_metric(
                session, principal, item, start=start, end=end, cohort_id=cohort_id
            )
            for item in ids
        ),
        generated_at=datetime.now(UTC),
    )


def get_accountability_outcome_summary(
    session: Session,
    principal: CurrentPrincipal,
    *,
    start: datetime,
    end: datetime,
    cohort_id: UUID | None = None,
) -> OutcomeSummary:
    _require(session, principal, "accountability.view")
    _population(principal, cohort_id)
    policy = _policy(session, principal)
    provenance = MetricProvenance(
        source_read_models=("interventions",),
        lineage_digest=_digest([start, end, principal.institution_id]),
        calculator=f"INTERVENTION_OUTCOME:{METRIC_VERSION}",
    )
    if policy is None:
        return OutcomeSummary(
            status="NOT_EVALUABLE",
            window_start=start,
            window_end=end,
            population=MetricPopulation(institution_id=principal.institution_id),
            observations={},
            total_interventions=0,
            missing_outcome_count=0,
            policy_version=None,
            freshness="UNKNOWN",
            provenance=provenance,
            reason="METRIC_POLICY_REQUIRED",
        )
    document, version = policy
    threshold = document.get("small_cell_threshold")
    row = session.exec(
        text(
            "SELECT count(*), count(*) FILTER (WHERE outcome_type IS NULL) FROM interventions WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND opened_at >= :start AND opened_at < :end"
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "start": start,
            "end": end,
        },
    ).first()
    total = int(row[0] or 0) if row else 0
    if not isinstance(threshold, int) or threshold < 1 or total < threshold:
        return OutcomeSummary(
            status="SUPPRESSED",
            window_start=start,
            window_end=end,
            population=MetricPopulation(institution_id=principal.institution_id),
            observations={},
            total_interventions=0,
            missing_outcome_count=0,
            policy_version=version,
            freshness="CURRENT",
            provenance=provenance,
            reason="SMALL_CELL_THRESHOLD"
            if isinstance(threshold, int)
            else "SMALL_CELL_POLICY_REQUIRED",
        )
    rows = session.exec(
        text(
            "SELECT COALESCE(outcome_type, 'MISSING'), count(*) FROM interventions WHERE organization_id=CAST(:organization_id AS uuid) AND institution_id=CAST(:institution_id AS uuid) AND opened_at >= :start AND opened_at < :end GROUP BY outcome_type"
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "start": start,
            "end": end,
        },
    ).all()
    observations: dict[str, int] = {}
    for raw_type, count in rows:
        canonical = _OUTCOME_MAP.get(
            str(raw_type), "INSUFFICIENT_EVIDENCE" if raw_type == "MISSING" else "UNRESOLVED"
        )
        observations[canonical] = observations.get(canonical, 0) + int(count)
    return OutcomeSummary(
        status="COMPUTED" if total else "NOT_COMPUTABLE",
        window_start=start,
        window_end=end,
        population=MetricPopulation(institution_id=principal.institution_id),
        observations=observations,
        total_interventions=total,
        missing_outcome_count=int(row[1] or 0) if row else 0,
        policy_version=version,
        freshness="CURRENT",
        provenance=provenance,
    )
