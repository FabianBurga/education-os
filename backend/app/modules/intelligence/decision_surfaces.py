from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.intelligence.access import (
    require_intelligence_manager_read,
    require_intelligence_read,
)
from app.modules.intelligence.schemas import (
    CohortIntelligenceRead,
    InstitutionIntelligenceAgentRead,
    IntelligenceOverviewRead,
    IntelligencePriorityItem,
    IntelligenceTrendPoint,
    InterventionHealthRead,
)

_PRIORITY_COLUMNS = {
    "ATTENDANCE": "attendance_priority",
    "ACADEMIC": "academic_priority",
    "INTERVENTION": "intervention_priority",
}


@dataclass(frozen=True, slots=True)
class ProjectionSlice:
    academic_period_id: UUID | None
    snapshot_date: date
    rule_set_version: int
    projection_version: int
    policy_source: str
    policy_key: str
    policy_version: int
    control_revision: int | None


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 100))


def _slice_params(item: ProjectionSlice) -> dict[str, object]:
    return {
        "academic_period_id": (
            str(item.academic_period_id)
            if item.academic_period_id is not None
            else None
        ),
        "snapshot_date": item.snapshot_date,
        "rule_set_version": item.rule_set_version,
        "projection_version": item.projection_version,
        "policy_source": item.policy_source,
        "policy_key": item.policy_key,
        "policy_version": item.policy_version,
    }


def _institution_slice(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    snapshot_date: date | None = None,
) -> ProjectionSlice | None:
    clauses = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
    ]
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
    }

    if academic_period_id is not None:
        clauses.append(
            "academic_period_id = CAST(:academic_period_id AS uuid)"
        )
        params["academic_period_id"] = str(academic_period_id)
    if snapshot_date is not None:
        clauses.append("snapshot_date = :snapshot_date")
        params["snapshot_date"] = snapshot_date

    row = session.exec(
        text(
            f"""
            SELECT
                academic_period_id,
                snapshot_date,
                rule_set_version,
                projection_version,
                policy_source,
                policy_key,
                policy_version,
                control_revision
            FROM institution_intelligence_daily
            WHERE {' AND '.join(clauses)}
            ORDER BY snapshot_date DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params=params,
    ).first()

    if row is None:
        return None

    return ProjectionSlice(
        academic_period_id=row[0],
        snapshot_date=row[1],
        rule_set_version=int(row[2]),
        projection_version=int(row[3]),
        policy_source=str(row[4]),
        policy_key=str(row[5]),
        policy_version=int(row[6]),
        control_revision=(int(row[7]) if row[7] is not None else None),
    )


def _student_slice(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    snapshot_date: date | None = None,
) -> ProjectionSlice | None:
    clauses = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
    ]
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
    }

    if academic_period_id is not None:
        clauses.append(
            "academic_period_id = CAST(:academic_period_id AS uuid)"
        )
        params["academic_period_id"] = str(academic_period_id)
    if snapshot_date is not None:
        clauses.append("snapshot_date = :snapshot_date")
        params["snapshot_date"] = snapshot_date

    row = session.exec(
        text(
            f"""
            SELECT
                academic_period_id,
                snapshot_date,
                rule_set_version,
                projection_version,
                policy_source,
                policy_key,
                policy_version,
                control_revision
            FROM student_intelligence_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY snapshot_date DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params=params,
    ).first()

    if row is None:
        return None

    return ProjectionSlice(
        academic_period_id=row[0],
        snapshot_date=row[1],
        rule_set_version=int(row[2]),
        projection_version=int(row[3]),
        policy_source=str(row[4]),
        policy_key=str(row[5]),
        policy_version=int(row[6]),
        control_revision=(int(row[7]) if row[7] is not None else None),
    )


def _priority_filter(
    *,
    priority: str | None,
    dimension: str | None,
) -> tuple[str | None, dict[str, object]]:
    if dimension is not None:
        column = _PRIORITY_COLUMNS[dimension]
        if priority is not None:
            return f"{column} = :priority", {"priority": priority}
        return f"{column} <> 'LOW'", {}

    if priority is not None:
        return "overall_priority = :priority", {"priority": priority}

    return None, {}


def _cohort_read(row) -> CohortIntelligenceRead:
    suppressed = bool(row[10])
    component_values = [
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
        row[9],
    ]
    if suppressed:
        component_values = [None] * 6

    return CohortIntelligenceRead(
        academic_period_id=row[0],
        snapshot_date=row[1],
        cohort_type=str(row[2]),
        cohort_ref_id=row[3],
        student_count=int(row[11]),
        high_priority_count=(
            int(component_values[0])
            if component_values[0] is not None
            else None
        ),
        medium_priority_count=(
            int(component_values[1])
            if component_values[1] is not None
            else None
        ),
        attendance_risk_count=(
            int(component_values[2])
            if component_values[2] is not None
            else None
        ),
        academic_risk_count=(
            int(component_values[3])
            if component_values[3] is not None
            else None
        ),
        active_intervention_count=(
            int(component_values[4])
            if component_values[4] is not None
            else None
        ),
        overdue_followup_count=(
            int(component_values[5])
            if component_values[5] is not None
            else None
        ),
        suppressed=suppressed,
        rule_set_version=int(row[12]),
        projection_version=int(row[13]),
        policy_source=str(row[14]),
        policy_version=int(row[15]),
        control_revision=(int(row[16]) if row[16] is not None else None),
    )


def intelligence_overview(
    session: Session,
    principal: CurrentPrincipal,
) -> IntelligenceOverviewRead:
    require_intelligence_manager_read(session, principal)
    slice_item = _institution_slice(session, principal)
    if slice_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence snapshot not found",
        )

    params = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        **_slice_params(slice_item),
    }
    row = session.exec(
        text(
            """
            SELECT
                i.academic_period_id,
                i.snapshot_date,
                i.in_scope_student_count,
                i.high_priority_count,
                i.medium_priority_count,
                i.active_intervention_count,
                i.interventions_without_action_count,
                i.overdue_followup_count,
                i.positive_outcome_count,
                i.unresolved_outcome_count,
                c.attendance_risk_count,
                c.academic_risk_count,
                c.suppressed,
                i.rule_set_version,
                i.projection_version,
                i.policy_source,
                i.policy_key,
                i.policy_version,
                i.control_revision
            FROM institution_intelligence_daily i
            LEFT JOIN cohort_intelligence_daily c
              ON c.organization_id = i.organization_id
             AND c.institution_id = i.institution_id
             AND c.snapshot_date = i.snapshot_date
             AND c.rule_set_version = i.rule_set_version
             AND c.projection_version = i.projection_version
             AND c.policy_source = i.policy_source
             AND c.policy_key = i.policy_key
             AND c.policy_version = i.policy_version
             AND c.academic_period_id IS NOT DISTINCT FROM i.academic_period_id
             AND c.cohort_type = 'INSTITUTION'
             AND c.cohort_ref_id IS NULL
            WHERE i.organization_id = CAST(:organization_id AS uuid)
              AND i.institution_id = CAST(:institution_id AS uuid)
              AND i.snapshot_date = :snapshot_date
              AND i.rule_set_version = :rule_set_version
              AND i.projection_version = :projection_version
              AND i.policy_source = :policy_source
              AND i.policy_key = :policy_key
              AND i.policy_version = :policy_version
              AND i.academic_period_id IS NOT DISTINCT FROM
                  CAST(:academic_period_id AS uuid)
            ORDER BY i.created_at DESC, i.id DESC
            LIMIT 1
            """
        ),
        params=params,
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence snapshot not found",
        )

    return IntelligenceOverviewRead(
        academic_period_id=row[0],
        snapshot_date=row[1],
        in_scope_student_count=int(row[2]),
        high_priority_count=int(row[3]),
        medium_priority_count=int(row[4]),
        active_intervention_count=int(row[5]),
        interventions_without_action_count=int(row[6]),
        overdue_followup_count=int(row[7]),
        positive_outcome_count=int(row[8]),
        unresolved_outcome_count=int(row[9]),
        attendance_risk_count=(
            None
            if bool(row[12])
            else (int(row[10]) if row[10] is not None else None)
        ),
        academic_risk_count=(
            None
            if bool(row[12])
            else (int(row[11]) if row[11] is not None else None)
        ),
        rule_set_version=int(row[13]),
        projection_version=int(row[14]),
        policy_source=str(row[15]),
        policy_key=str(row[16]),
        policy_version=int(row[17]),
        control_revision=(int(row[18]) if row[18] is not None else None),
    )


def inspect_current_institution_intelligence(
    session: Session,
    principal: CurrentPrincipal,
) -> InstitutionIntelligenceAgentRead:
    """Return a minimized current M22 snapshot under permission-only access.

    This is an internal M22 read boundary.  It deliberately avoids the
    management-role decision surfaces: M25 separately requires agents.use and
    may reveal no more than this typed, aggregate intelligence view.
    """
    require_intelligence_read(session, principal)
    row = session.exec(
        text(
            """
            SELECT id, snapshot_date, created_at, policy_key, policy_version,
                   rule_set_version, projection_version
            FROM institution_intelligence_daily
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            ORDER BY snapshot_date DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence snapshot not found",
        )

    signal_row = session.exec(
        text(
            """
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE severity = 'LOW'),
                COUNT(*) FILTER (WHERE severity = 'MEDIUM'),
                COUNT(*) FILTER (WHERE severity = 'HIGH')
            FROM intelligence_signals
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'OPEN'
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).one()
    categories = session.exec(
        text(
            """
            SELECT signal_type
            FROM intelligence_signals
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'OPEN'
            GROUP BY signal_type
            ORDER BY COUNT(*) DESC, signal_type
            LIMIT 10
            """
        ),
        params={
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).all()
    return InstitutionIntelligenceAgentRead(
        snapshot_id=row[0], snapshot_date=row[1], generated_at=row[2],
        policy_key=str(row[3]), policy_version=int(row[4]),
        rule_set_version=int(row[5]), projection_version=int(row[6]),
        open_signal_total=int(signal_row[0] or 0),
        open_signal_low=int(signal_row[1] or 0),
        open_signal_medium=int(signal_row[2] or 0),
        open_signal_high=int(signal_row[3] or 0),
        top_signal_categories=[str(item[0]) for item in categories],
    )


def list_intelligence_priorities(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    snapshot_date: date | None = None,
    priority: str | None = None,
    dimension: str | None = None,
    limit: int = 50,
) -> list[IntelligencePriorityItem]:
    require_intelligence_read(session, principal)
    slice_item = _student_slice(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )
    if slice_item is None:
        return []

    clauses = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
        "snapshot_date = :snapshot_date",
        "rule_set_version = :rule_set_version",
        "projection_version = :projection_version",
        "policy_source = :policy_source",
        "policy_key = :policy_key",
        "policy_version = :policy_version",
        "academic_period_id IS NOT DISTINCT FROM "
        "CAST(:academic_period_id AS uuid)",
    ]
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        **_slice_params(slice_item),
        "limit": _bounded_limit(limit),
    }

    filter_sql, filter_params = _priority_filter(
        priority=priority,
        dimension=dimension,
    )
    if filter_sql is not None:
        clauses.append(filter_sql)
        params.update(filter_params)

    rows = session.exec(
        text(
            f"""
            SELECT
                student_profile_id,
                academic_period_id,
                snapshot_date,
                overall_priority,
                attendance_priority,
                academic_priority,
                intervention_priority,
                evidence_count,
                rule_set_version,
                projection_version,
                policy_source,
                policy_version,
                control_revision
            FROM student_intelligence_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE overall_priority
                    WHEN 'HIGH' THEN 3
                    WHEN 'MEDIUM' THEN 2
                    ELSE 1
                END DESC,
                evidence_count DESC,
                student_profile_id
            LIMIT :limit
            """
        ),
        params=params,
    ).all()

    return [
        IntelligencePriorityItem(
            student_profile_id=row[0],
            academic_period_id=row[1],
            snapshot_date=row[2],
            overall_priority=str(row[3]),
            attendance_priority=str(row[4]),
            academic_priority=str(row[5]),
            intervention_priority=str(row[6]),
            evidence_count=int(row[7]),
            rule_set_version=int(row[8]),
            projection_version=int(row[9]),
            policy_source=str(row[10]),
            policy_version=int(row[11]),
            control_revision=(int(row[12]) if row[12] is not None else None),
        )
        for row in rows
    ]


def list_intelligence_cohorts(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    snapshot_date: date | None = None,
    cohort_type: str | None = None,
    limit: int = 100,
) -> list[CohortIntelligenceRead]:
    require_intelligence_manager_read(session, principal)
    slice_item = _institution_slice(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )
    if slice_item is None:
        return []

    clauses = [
        "organization_id = CAST(:organization_id AS uuid)",
        "institution_id = CAST(:institution_id AS uuid)",
        "snapshot_date = :snapshot_date",
        "rule_set_version = :rule_set_version",
        "projection_version = :projection_version",
        "policy_source = :policy_source",
        "policy_key = :policy_key",
        "policy_version = :policy_version",
        "academic_period_id IS NOT DISTINCT FROM "
        "CAST(:academic_period_id AS uuid)",
    ]
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        **_slice_params(slice_item),
        "limit": _bounded_limit(limit),
    }
    if cohort_type is not None:
        clauses.append("cohort_type = :cohort_type")
        params["cohort_type"] = cohort_type

    rows = session.exec(
        text(
            f"""
            SELECT
                academic_period_id,
                snapshot_date,
                cohort_type,
                cohort_ref_id,
                high_priority_count,
                medium_priority_count,
                attendance_risk_count,
                academic_risk_count,
                active_intervention_count,
                overdue_followup_count,
                suppressed,
                student_count,
                rule_set_version,
                projection_version,
                policy_source,
                policy_version,
                control_revision
            FROM cohort_intelligence_daily
            WHERE {' AND '.join(clauses)}
            ORDER BY
                CASE cohort_type
                    WHEN 'INSTITUTION' THEN 1
                    WHEN 'ACADEMIC_LEVEL' THEN 2
                    WHEN 'GRADE' THEN 3
                    WHEN 'SECTION' THEN 4
                    ELSE 5
                END,
                cohort_ref_id NULLS FIRST
            LIMIT :limit
            """
        ),
        params=params,
    ).all()

    return [_cohort_read(row) for row in rows]


def intelligence_trends(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    days: int = 30,
) -> list[IntelligenceTrendPoint]:
    require_intelligence_manager_read(session, principal)
    slice_item = _institution_slice(
        session,
        principal,
        academic_period_id=academic_period_id,
    )
    if slice_item is None:
        return []

    bounded_days = max(2, min(int(days), 365))
    cutoff = slice_item.snapshot_date - timedelta(days=bounded_days - 1)
    period_clause = ""
    params: dict[str, object] = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        "cutoff": cutoff,
        "latest": slice_item.snapshot_date,
    }
    if academic_period_id is not None:
        period_clause = (
            "AND academic_period_id = CAST(:academic_period_id AS uuid)"
        )
        params["academic_period_id"] = str(academic_period_id)

    rows = session.exec(
        text(
            f"""
            WITH latest_per_day AS (
                SELECT DISTINCT ON (snapshot_date)
                    id,
                    organization_id,
                    institution_id,
                    academic_period_id,
                    snapshot_date,
                    in_scope_student_count,
                    high_priority_count,
                    medium_priority_count,
                    active_intervention_count,
                    overdue_followup_count,
                    positive_outcome_count,
                    unresolved_outcome_count,
                    rule_set_version,
                    projection_version,
                    policy_source,
                    policy_key,
                    policy_version,
                    created_at
                FROM institution_intelligence_daily
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND snapshot_date >= :cutoff
                  AND snapshot_date <= :latest
                  {period_clause}
                ORDER BY snapshot_date, created_at DESC, id DESC
            )
            SELECT
                i.snapshot_date,
                i.in_scope_student_count,
                i.high_priority_count,
                i.medium_priority_count,
                c.attendance_risk_count,
                c.academic_risk_count,
                c.suppressed,
                i.active_intervention_count,
                i.overdue_followup_count,
                i.positive_outcome_count,
                i.unresolved_outcome_count
            FROM latest_per_day i
            LEFT JOIN cohort_intelligence_daily c
              ON c.organization_id = i.organization_id
             AND c.institution_id = i.institution_id
             AND c.snapshot_date = i.snapshot_date
             AND c.rule_set_version = i.rule_set_version
             AND c.projection_version = i.projection_version
             AND c.policy_source = i.policy_source
             AND c.policy_key = i.policy_key
             AND c.policy_version = i.policy_version
             AND c.academic_period_id IS NOT DISTINCT FROM i.academic_period_id
             AND c.cohort_type = 'INSTITUTION'
             AND c.cohort_ref_id IS NULL
            ORDER BY i.snapshot_date
            """
        ),
        params=params,
    ).all()

    return [
        IntelligenceTrendPoint(
            snapshot_date=row[0],
            in_scope_student_count=int(row[1]),
            high_priority_count=int(row[2]),
            medium_priority_count=int(row[3]),
            attendance_risk_count=(
                None
                if bool(row[6])
                else (int(row[4]) if row[4] is not None else None)
            ),
            academic_risk_count=(
                None
                if bool(row[6])
                else (int(row[5]) if row[5] is not None else None)
            ),
            active_intervention_count=int(row[7]),
            overdue_followup_count=int(row[8]),
            positive_outcome_count=int(row[9]),
            unresolved_outcome_count=int(row[10]),
        )
        for row in rows
    ]


def intervention_health(
    session: Session,
    principal: CurrentPrincipal,
    *,
    academic_period_id: UUID | None = None,
    snapshot_date: date | None = None,
) -> InterventionHealthRead:
    require_intelligence_manager_read(session, principal)
    slice_item = _institution_slice(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )
    if slice_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence snapshot not found",
        )

    params = {
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
        **_slice_params(slice_item),
    }
    row = session.exec(
        text(
            """
            SELECT
                academic_period_id,
                snapshot_date,
                active_intervention_count,
                interventions_without_action_count,
                overdue_followup_count,
                positive_outcome_count,
                unresolved_outcome_count,
                policy_source,
                policy_version,
                control_revision
            FROM institution_intelligence_daily
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND snapshot_date = :snapshot_date
              AND rule_set_version = :rule_set_version
              AND projection_version = :projection_version
              AND policy_source = :policy_source
              AND policy_key = :policy_key
              AND policy_version = :policy_version
              AND academic_period_id IS NOT DISTINCT FROM
                  CAST(:academic_period_id AS uuid)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        params=params,
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence snapshot not found",
        )

    return InterventionHealthRead(
        academic_period_id=row[0],
        snapshot_date=row[1],
        active_interventions=int(row[2]),
        interventions_without_action=int(row[3]),
        followup_overdue=int(row[4]),
        positive_outcomes=int(row[5]),
        unresolved_outcomes=int(row[6]),
        policy_source=str(row[7]),
        policy_version=int(row[8]),
        control_revision=(int(row[9]) if row[9] is not None else None),
    )
