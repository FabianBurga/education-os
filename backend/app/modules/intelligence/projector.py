from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.modules.intelligence.policy import (
    ResolvedIntelligencePolicy,
    resolve_intelligence_policy,
)
from app.modules.intelligence.rules import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    RULE_SET_VERSION,
    InterventionFacts,
    evaluate_academic_priority,
    evaluate_attendance_priority,
    evaluate_intervention_priority,
    highest_priority,
)

PROJECTION_VERSION = 1

ACTIVE_INTERVENTION_STATUSES = (
    "OPEN",
    "IN_PROGRESS",
    "MONITORING",
)
UNRESOLVED_OUTCOMES = (
    "NO_CHANGE",
    "WORSENED",
    "NOT_ASSESSABLE",
)


@dataclass(slots=True)
class StudentDimensions:
    section_ids: set[UUID] = field(default_factory=set)
    grade_level_ids: set[UUID] = field(default_factory=set)
    academic_level_ids: set[UUID] = field(default_factory=set)
    course_offering_ids: set[UUID] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class AcademicFacts:
    graded_count: int = 0
    average_percent: float | None = None
    missing_count: int = 0
    previous_average_percent: float | None = None


@dataclass(frozen=True, slots=True)
class AttendanceFacts:
    total_records: int = 0
    absence_percent: float | None = None
    late_count: int = 0


@dataclass(frozen=True, slots=True)
class StudentProjection:
    student_profile_id: UUID
    attendance_priority: str
    academic_priority: str
    intervention_priority: str
    overall_priority: str
    evidence_count: int
    intervention_facts: InterventionFacts


@dataclass(frozen=True, slots=True)
class IntelligenceProjectionStats:
    student_snapshots: int
    cohort_snapshots: int
    suppressed_cohorts: int
    high_priority_students: int
    medium_priority_students: int
    active_interventions: int
    policy_source: str
    policy_version: int
    control_revision: int | None


def _roster(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
) -> dict[UUID, StudentDimensions]:
    rows = session.exec(
        text(
            """
            SELECT DISTINCT
                e.student_profile_id,
                ssa.section_id,
                s.grade_level_id,
                gl.academic_level_id
            FROM student_section_assignments ssa
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.organization_id = ssa.organization_id
             AND e.institution_id = ssa.institution_id
            JOIN sections s
              ON s.id = ssa.section_id
             AND s.organization_id = ssa.organization_id
             AND s.institution_id = ssa.institution_id
            JOIN grade_levels gl
              ON gl.id = s.grade_level_id
             AND gl.organization_id = s.organization_id
             AND gl.institution_id = s.institution_id
            WHERE ssa.organization_id = CAST(:organization_id AS uuid)
              AND ssa.institution_id = CAST(:institution_id AS uuid)
              AND ssa.academic_period_id = CAST(:academic_period_id AS uuid)
              AND ssa.status = 'ACTIVE'
              AND e.status = 'ACTIVE'
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
        },
    ).all()

    result: dict[UUID, StudentDimensions] = {}
    section_students: dict[UUID, set[UUID]] = {}

    for student_id, section_id, grade_level_id, academic_level_id in rows:
        dims = result.setdefault(student_id, StudentDimensions())
        dims.section_ids.add(section_id)
        dims.grade_level_ids.add(grade_level_id)
        dims.academic_level_ids.add(academic_level_id)
        section_students.setdefault(section_id, set()).add(student_id)

    if not section_students:
        return result

    course_rows = session.exec(
        text(
            """
            SELECT id, section_id
            FROM course_offerings
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND academic_period_id = CAST(:academic_period_id AS uuid)
              AND status = 'ACTIVE'
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
        },
    ).all()

    for course_offering_id, section_id in course_rows:
        for student_id in section_students.get(section_id, ()):
            result[student_id].course_offering_ids.add(course_offering_id)

    return result


def _attendance_facts(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    window_start: datetime,
    window_end: datetime,
) -> dict[UUID, AttendanceFacts]:
    rows = session.exec(
        text(
            """
            SELECT
                e.student_profile_id,
                COUNT(ar.id) AS total_records,
                COUNT(ar.id) FILTER (
                    WHERE ac.counts_as_absent
                ) AS absent_count,
                COUNT(ar.id) FILTER (
                    WHERE ac.counts_as_late
                ) AS late_count
            FROM attendance_records ar
            JOIN attendance_codes ac
              ON ac.id = ar.attendance_code_id
             AND ac.organization_id = ar.organization_id
             AND ac.institution_id = ar.institution_id
            JOIN class_sessions cs
              ON cs.id = ar.class_session_id
             AND cs.organization_id = ar.organization_id
             AND cs.institution_id = ar.institution_id
            JOIN student_section_assignments ssa
              ON ssa.id = ar.student_section_assignment_id
             AND ssa.organization_id = ar.organization_id
             AND ssa.institution_id = ar.institution_id
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.organization_id = ssa.organization_id
             AND e.institution_id = ssa.institution_id
            WHERE ar.organization_id = CAST(:organization_id AS uuid)
              AND ar.institution_id = CAST(:institution_id AS uuid)
              AND ssa.academic_period_id = CAST(:academic_period_id AS uuid)
              AND ssa.status = 'ACTIVE'
              AND e.status = 'ACTIVE'
              AND cs.session_date >= :window_start_date
              AND cs.session_date <= :window_end_date
            GROUP BY e.student_profile_id
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
            "window_start_date": window_start.date(),
            "window_end_date": window_end.date(),
        },
    ).all()

    result: dict[UUID, AttendanceFacts] = {}
    for student_id, total, absent, late in rows:
        total_int = int(total or 0)
        absent_int = int(absent or 0)
        result[student_id] = AttendanceFacts(
            total_records=total_int,
            absence_percent=(
                round((absent_int / total_int) * 100.0, 2)
                if total_int
                else None
            ),
            late_count=int(late or 0),
        )
    return result


def _grading_periods(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
) -> tuple[UUID | None, UUID | None]:
    rows = session.exec(
        text(
            """
            SELECT id
            FROM grading_periods
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND academic_period_id = CAST(:academic_period_id AS uuid)
              AND starts_on <= :snapshot_date
            ORDER BY sequence DESC, starts_on DESC, id
            LIMIT 2
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
            "snapshot_date": snapshot_date,
        },
    ).all()

    current_id = rows[0][0] if rows else None
    previous_id = rows[1][0] if len(rows) > 1 else None
    return current_id, previous_id


def _grading_period_facts(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    grading_period_id: UUID | None,
) -> dict[UUID, tuple[int, float | None, int]]:
    if grading_period_id is None:
        return {}

    rows = session.exec(
        text(
            """
            SELECT
                e.student_profile_id,
                COUNT(ge.id) FILTER (
                    WHERE ge.status = 'GRADED'
                      AND ge.score IS NOT NULL
                ) AS graded_count,
                AVG(
                    (ge.score / NULLIF(a.max_score, 0)) * 100.0
                ) FILTER (
                    WHERE ge.status = 'GRADED'
                      AND ge.score IS NOT NULL
                ) AS average_percent,
                COUNT(ge.id) FILTER (
                    WHERE ge.status = 'MISSING'
                ) AS missing_count
            FROM student_section_assignments ssa
            JOIN enrollments e
              ON e.id = ssa.enrollment_id
             AND e.organization_id = ssa.organization_id
             AND e.institution_id = ssa.institution_id
            LEFT JOIN grade_entries ge
              ON ge.student_section_assignment_id = ssa.id
             AND ge.organization_id = ssa.organization_id
             AND ge.institution_id = ssa.institution_id
            LEFT JOIN assessments a
              ON a.id = ge.assessment_id
             AND a.organization_id = ge.organization_id
             AND a.institution_id = ge.institution_id
            WHERE ssa.organization_id = CAST(:organization_id AS uuid)
              AND ssa.institution_id = CAST(:institution_id AS uuid)
              AND ssa.academic_period_id = CAST(:academic_period_id AS uuid)
              AND ssa.status = 'ACTIVE'
              AND e.status = 'ACTIVE'
              AND a.grading_period_id = CAST(:grading_period_id AS uuid)
            GROUP BY e.student_profile_id
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
            "grading_period_id": str(grading_period_id),
        },
    ).all()

    return {
        student_id: (
            int(graded or 0),
            round(float(average), 2) if average is not None else None,
            int(missing or 0),
        )
        for student_id, graded, average, missing in rows
    }


def _academic_facts(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
) -> dict[UUID, AcademicFacts]:
    current_id, previous_id = _grading_periods(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )
    current = _grading_period_facts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        grading_period_id=current_id,
    )
    previous = _grading_period_facts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        grading_period_id=previous_id,
    )

    student_ids = set(current) | set(previous)
    result: dict[UUID, AcademicFacts] = {}
    for student_id in student_ids:
        graded, average, missing = current.get(
            student_id,
            (0, None, 0),
        )
        previous_average = previous.get(
            student_id,
            (0, None, 0),
        )[1]
        result[student_id] = AcademicFacts(
            graded_count=graded,
            average_percent=average,
            missing_count=missing,
            previous_average_percent=previous_average,
        )
    return result


def _intervention_facts(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    followup_cutoff: datetime,
) -> dict[UUID, InterventionFacts]:
    rows = session.exec(
        text(
            """
            SELECT
                i.student_profile_id,
                COUNT(*) FILTER (
                    WHERE i.status IN ('OPEN','IN_PROGRESS','MONITORING')
                ) AS active_count,
                COUNT(*) FILTER (
                    WHERE i.status IN ('OPEN','IN_PROGRESS','MONITORING')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM intervention_actions ia
                          WHERE ia.intervention_id = i.id
                            AND ia.organization_id = i.organization_id
                            AND ia.institution_id = i.institution_id
                            AND ia.status <> 'CANCELLED'
                      )
                ) AS without_action_count,
                COUNT(*) FILTER (
                    WHERE i.status IN ('OPEN','IN_PROGRESS','MONITORING')
                      AND COALESCE(
                          (
                              SELECT MAX(f.observed_at)
                              FROM intervention_followups f
                              WHERE f.intervention_id = i.id
                                AND f.organization_id = i.organization_id
                                AND f.institution_id = i.institution_id
                          ),
                          i.opened_at
                      ) < :followup_cutoff
                ) AS overdue_followup_count,
                COUNT(*) FILTER (
                    WHERE i.status IN ('RESOLVED','CLOSED')
                      AND i.outcome_type IN (
                          'NO_CHANGE',
                          'WORSENED',
                          'NOT_ASSESSABLE'
                      )
                ) AS unresolved_outcome_count,
                COUNT(*) FILTER (
                    WHERE i.status IN ('RESOLVED','CLOSED')
                      AND i.outcome_type = 'WORSENED'
                ) AS worsened_outcome_count,
                COUNT(*) FILTER (
                    WHERE i.status IN ('RESOLVED','CLOSED')
                      AND i.outcome_type = 'IMPROVED'
                ) AS positive_outcome_count
            FROM interventions i
            WHERE i.organization_id = CAST(:organization_id AS uuid)
              AND i.institution_id = CAST(:institution_id AS uuid)
              AND (
                  i.academic_period_id IS NULL
                  OR i.academic_period_id = CAST(:academic_period_id AS uuid)
              )
            GROUP BY i.student_profile_id
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
            "followup_cutoff": followup_cutoff,
        },
    ).all()

    return {
        student_id: InterventionFacts(
            active_count=int(active or 0),
            without_action_count=int(without_action or 0),
            overdue_followup_count=int(overdue or 0),
            unresolved_outcome_count=int(unresolved or 0),
            worsened_outcome_count=int(worsened or 0),
            positive_outcome_count=int(positive or 0),
        )
        for (
            student_id,
            active,
            without_action,
            overdue,
            unresolved,
            worsened,
            positive,
        ) in rows
    }


def _open_signal_counts(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
) -> dict[UUID, int]:
    rows = session.exec(
        text(
            """
            SELECT student_profile_id, COUNT(*)
            FROM intelligence_signals
            WHERE organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'OPEN'
              AND (
                  academic_period_id IS NULL
                  OR academic_period_id = CAST(:academic_period_id AS uuid)
              )
            GROUP BY student_profile_id
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
        },
    ).all()
    return {
        student_id: int(count or 0)
        for student_id, count in rows
    }


def _projection_identity(policy: ResolvedIntelligencePolicy) -> dict[str, Any]:
    return {
        "rule_set_version": RULE_SET_VERSION,
        "projection_version": PROJECTION_VERSION,
        "policy_source": policy.policy_source,
        "policy_key": policy.policy_key,
        "policy_version": policy.policy_version,
        "control_revision": policy.control_revision,
    }


def _clear_projection_slice(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    snapshot_date: date,
    policy: ResolvedIntelligencePolicy,
) -> None:
    params = {
        "organization_id": str(organization_id),
        "institution_id": str(institution_id),
        "snapshot_date": snapshot_date,
        **_projection_identity(policy),
    }

    for table in (
        "cohort_intelligence_daily",
        "institution_intelligence_daily",
        "student_intelligence_snapshots",
    ):
        session.exec(
            text(
                f"""
                DELETE FROM {table}
                WHERE organization_id = CAST(:organization_id AS uuid)
                  AND institution_id = CAST(:institution_id AS uuid)
                  AND snapshot_date = :snapshot_date
                  AND rule_set_version = :rule_set_version
                  AND projection_version = :projection_version
                  AND policy_source = :policy_source
                  AND policy_key = :policy_key
                  AND policy_version = :policy_version
                """
            ),
            params=params,
        )


def _student_projections(
    roster: dict[UUID, StudentDimensions],
    attendance: dict[UUID, AttendanceFacts],
    academics: dict[UUID, AcademicFacts],
    interventions: dict[UUID, InterventionFacts],
    signal_counts: dict[UUID, int],
    *,
    policy: ResolvedIntelligencePolicy,
) -> dict[UUID, StudentProjection]:
    result: dict[UUID, StudentProjection] = {}

    for student_id in sorted(roster, key=str):
        attendance_facts = attendance.get(
            student_id,
            AttendanceFacts(),
        )
        academic_facts = academics.get(
            student_id,
            AcademicFacts(),
        )
        intervention_facts = interventions.get(
            student_id,
            InterventionFacts(),
        )

        attendance_result = evaluate_attendance_priority(
            total_records=attendance_facts.total_records,
            absence_percent=attendance_facts.absence_percent,
            late_count=attendance_facts.late_count,
            policy=policy,
        )
        academic_result = evaluate_academic_priority(
            graded_count=academic_facts.graded_count,
            average_percent=academic_facts.average_percent,
            missing_count=academic_facts.missing_count,
            previous_average_percent=academic_facts.previous_average_percent,
            policy=policy,
        )
        intervention_result = evaluate_intervention_priority(
            intervention_facts,
        )
        overall = highest_priority(
            attendance_result.priority,
            academic_result.priority,
            intervention_result.priority,
        )

        matched_rule_count = (
            len(attendance_result.matched_rules)
            + len(academic_result.matched_rules)
            + len(intervention_result.matched_rules)
        )
        evidence_count = matched_rule_count + signal_counts.get(
            student_id,
            0,
        )

        result[student_id] = StudentProjection(
            student_profile_id=student_id,
            attendance_priority=attendance_result.priority,
            academic_priority=academic_result.priority,
            intervention_priority=intervention_result.priority,
            overall_priority=overall,
            evidence_count=evidence_count,
            intervention_facts=intervention_facts,
        )

    return result


def _insert_student_snapshots(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
    evaluated_at: datetime,
    window_start: datetime,
    window_end: datetime,
    policy: ResolvedIntelligencePolicy,
    projections: dict[UUID, StudentProjection],
) -> None:
    identity = _projection_identity(policy)

    for student_id in sorted(projections, key=str):
        item = projections[student_id]
        session.exec(
            text(
                """
                INSERT INTO student_intelligence_snapshots (
                    id,
                    organization_id,
                    institution_id,
                    student_profile_id,
                    academic_period_id,
                    snapshot_date,
                    evaluated_at,
                    overall_priority,
                    attendance_priority,
                    academic_priority,
                    intervention_priority,
                    evidence_count,
                    rule_set_version,
                    projection_version,
                    policy_source,
                    policy_key,
                    policy_version,
                    control_revision,
                    window_start,
                    window_end,
                    created_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    CAST(:student_profile_id AS uuid),
                    CAST(:academic_period_id AS uuid),
                    :snapshot_date,
                    :evaluated_at,
                    :overall_priority,
                    :attendance_priority,
                    :academic_priority,
                    :intervention_priority,
                    :evidence_count,
                    :rule_set_version,
                    :projection_version,
                    :policy_source,
                    :policy_key,
                    :policy_version,
                    :control_revision,
                    :window_start,
                    :window_end,
                    NOW()
                )
                """
            ),
            params={
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "institution_id": str(institution_id),
                "student_profile_id": str(student_id),
                "academic_period_id": str(academic_period_id),
                "snapshot_date": snapshot_date,
                "evaluated_at": evaluated_at,
                "overall_priority": item.overall_priority,
                "attendance_priority": item.attendance_priority,
                "academic_priority": item.academic_priority,
                "intervention_priority": item.intervention_priority,
                "evidence_count": item.evidence_count,
                **identity,
                "window_start": window_start,
                "window_end": window_end,
            },
        )


def _cohort_memberships(
    roster: dict[UUID, StudentDimensions],
) -> dict[tuple[str, UUID | None], set[UUID]]:
    memberships: dict[tuple[str, UUID | None], set[UUID]] = {
        ("INSTITUTION", None): set(roster),
    }

    for student_id, dims in roster.items():
        for ref_id in dims.academic_level_ids:
            memberships.setdefault(
                ("ACADEMIC_LEVEL", ref_id),
                set(),
            ).add(student_id)
        for ref_id in dims.grade_level_ids:
            memberships.setdefault(
                ("GRADE", ref_id),
                set(),
            ).add(student_id)
        for ref_id in dims.section_ids:
            memberships.setdefault(
                ("SECTION", ref_id),
                set(),
            ).add(student_id)
        for ref_id in dims.course_offering_ids:
            memberships.setdefault(
                ("COURSE", ref_id),
                set(),
            ).add(student_id)

    return memberships


def _insert_cohort_snapshots(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
    policy: ResolvedIntelligencePolicy,
    roster: dict[UUID, StudentDimensions],
    projections: dict[UUID, StudentProjection],
) -> tuple[int, int]:
    identity = _projection_identity(policy)
    memberships = _cohort_memberships(roster)
    suppressed_count = 0

    for cohort_type, cohort_ref_id in sorted(
        memberships,
        key=lambda item: (item[0], str(item[1] or "")),
    ):
        student_ids = memberships[(cohort_type, cohort_ref_id)]
        student_count = len(student_ids)
        suppressed = (
            student_count < policy.privacy.minimum_cohort_size
        )

        if suppressed:
            suppressed_count += 1
            counts: dict[str, int | None] = {
                "high_priority_count": None,
                "medium_priority_count": None,
                "attendance_risk_count": None,
                "academic_risk_count": None,
                "active_intervention_count": None,
                "overdue_followup_count": None,
            }
        else:
            items = [projections[sid] for sid in student_ids]
            counts = {
                "high_priority_count": sum(
                    item.overall_priority == PRIORITY_HIGH
                    for item in items
                ),
                "medium_priority_count": sum(
                    item.overall_priority == PRIORITY_MEDIUM
                    for item in items
                ),
                "attendance_risk_count": sum(
                    item.attendance_priority != PRIORITY_LOW
                    for item in items
                ),
                "academic_risk_count": sum(
                    item.academic_priority != PRIORITY_LOW
                    for item in items
                ),
                "active_intervention_count": sum(
                    item.intervention_facts.active_count
                    for item in items
                ),
                "overdue_followup_count": sum(
                    item.intervention_facts.overdue_followup_count
                    for item in items
                ),
            }

        session.exec(
            text(
                """
                INSERT INTO cohort_intelligence_daily (
                    id,
                    organization_id,
                    institution_id,
                    academic_period_id,
                    snapshot_date,
                    cohort_type,
                    cohort_ref_id,
                    student_count,
                    high_priority_count,
                    medium_priority_count,
                    attendance_risk_count,
                    academic_risk_count,
                    active_intervention_count,
                    overdue_followup_count,
                    suppressed,
                    rule_set_version,
                    projection_version,
                    policy_source,
                    policy_key,
                    policy_version,
                    control_revision,
                    created_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    CAST(:academic_period_id AS uuid),
                    :snapshot_date,
                    :cohort_type,
                    CAST(:cohort_ref_id AS uuid),
                    :student_count,
                    :high_priority_count,
                    :medium_priority_count,
                    :attendance_risk_count,
                    :academic_risk_count,
                    :active_intervention_count,
                    :overdue_followup_count,
                    :suppressed,
                    :rule_set_version,
                    :projection_version,
                    :policy_source,
                    :policy_key,
                    :policy_version,
                    :control_revision,
                    NOW()
                )
                """
            ),
            params={
                "id": str(uuid4()),
                "organization_id": str(organization_id),
                "institution_id": str(institution_id),
                "academic_period_id": str(academic_period_id),
                "snapshot_date": snapshot_date,
                "cohort_type": cohort_type,
                "cohort_ref_id": (
                    str(cohort_ref_id)
                    if cohort_ref_id is not None
                    else None
                ),
                "student_count": student_count,
                **counts,
                "suppressed": suppressed,
                **identity,
            },
        )

    return len(memberships), suppressed_count


def _insert_institution_snapshot(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
    policy: ResolvedIntelligencePolicy,
    projections: dict[UUID, StudentProjection],
) -> None:
    identity = _projection_identity(policy)
    items = list(projections.values())

    session.exec(
        text(
            """
            INSERT INTO institution_intelligence_daily (
                id,
                organization_id,
                institution_id,
                academic_period_id,
                snapshot_date,
                in_scope_student_count,
                high_priority_count,
                medium_priority_count,
                active_intervention_count,
                interventions_without_action_count,
                overdue_followup_count,
                positive_outcome_count,
                unresolved_outcome_count,
                rule_set_version,
                projection_version,
                policy_source,
                policy_key,
                policy_version,
                control_revision,
                created_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                CAST(:academic_period_id AS uuid),
                :snapshot_date,
                :in_scope_student_count,
                :high_priority_count,
                :medium_priority_count,
                :active_intervention_count,
                :interventions_without_action_count,
                :overdue_followup_count,
                :positive_outcome_count,
                :unresolved_outcome_count,
                :rule_set_version,
                :projection_version,
                :policy_source,
                :policy_key,
                :policy_version,
                :control_revision,
                NOW()
            )
            """
        ),
        params={
            "id": str(uuid4()),
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "academic_period_id": str(academic_period_id),
            "snapshot_date": snapshot_date,
            "in_scope_student_count": len(items),
            "high_priority_count": sum(
                item.overall_priority == PRIORITY_HIGH
                for item in items
            ),
            "medium_priority_count": sum(
                item.overall_priority == PRIORITY_MEDIUM
                for item in items
            ),
            "active_intervention_count": sum(
                item.intervention_facts.active_count
                for item in items
            ),
            "interventions_without_action_count": sum(
                item.intervention_facts.without_action_count
                for item in items
            ),
            "overdue_followup_count": sum(
                item.intervention_facts.overdue_followup_count
                for item in items
            ),
            "positive_outcome_count": sum(
                item.intervention_facts.positive_outcome_count
                for item in items
            ),
            "unresolved_outcome_count": sum(
                item.intervention_facts.unresolved_outcome_count
                for item in items
            ),
            **identity,
        },
    )


def project_institution_intelligence(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    academic_period_id: UUID,
    snapshot_date: date,
    window_start: datetime,
    window_end: datetime,
) -> IntelligenceProjectionStats:
    """Build deterministic M22 analytical snapshots for one institution/day.

    The attendance window is explicit. Academic risk is evaluated against
    grading periods. Intervention health uses calendar-time thresholds.
    The function does not commit; the caller owns transaction boundaries.
    """
    if window_end < window_start:
        raise ValueError("window_end must be >= window_start")

    policy = resolve_intelligence_policy(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    roster = _roster(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
    )
    attendance = _attendance_facts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        window_start=window_start,
        window_end=window_end,
    )
    academics = _academic_facts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )
    interventions = _intervention_facts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        followup_cutoff=(
            window_end
            - timedelta(
                days=policy.intervention.followup_overdue_calendar_days
            )
        ),
    )
    signal_counts = _open_signal_counts(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
    )

    projections = _student_projections(
        roster,
        attendance,
        academics,
        interventions,
        signal_counts,
        policy=policy,
    )

    _clear_projection_slice(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        snapshot_date=snapshot_date,
        policy=policy,
    )
    _insert_student_snapshots(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
        evaluated_at=window_end,
        window_start=window_start,
        window_end=window_end,
        policy=policy,
        projections=projections,
    )
    cohort_count, suppressed_count = _insert_cohort_snapshots(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
        policy=policy,
        roster=roster,
        projections=projections,
    )
    _insert_institution_snapshot(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
        policy=policy,
        projections=projections,
    )

    values = list(projections.values())
    return IntelligenceProjectionStats(
        student_snapshots=len(values),
        cohort_snapshots=cohort_count,
        suppressed_cohorts=suppressed_count,
        high_priority_students=sum(
            item.overall_priority == PRIORITY_HIGH
            for item in values
        ),
        medium_priority_students=sum(
            item.overall_priority == PRIORITY_MEDIUM
            for item in values
        ),
        active_interventions=sum(
            item.intervention_facts.active_count
            for item in values
        ),
        policy_source=policy.policy_source,
        policy_version=policy.policy_version,
        control_revision=policy.control_revision,
    )
