from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.events.service import enqueue_canonical_event
from app.modules.intelligence.models import IntelligenceSignal
from app.modules.intelligence.schemas import (
    AcademicTrendPoint,
    AttendanceTrendPoint,
    RectorOverview,
    SectionIntelligence,
    SignalRefreshResult,
    SignalResolve,
)

ATTENDANCE_ABSENCE_THRESHOLD = 20.0
ATTENDANCE_MIN_RECORDS = 5
LATE_COUNT_THRESHOLD = 3.0
ACADEMIC_AVERAGE_THRESHOLD = 70.0
ACADEMIC_MIN_GRADED = 2
MISSING_WORK_THRESHOLD = 3.0


def _scalar(session: Session, sql: str, **params):
    row = session.exec(text(sql).bindparams(**params)).first()
    if row is None:
        return None
    return row[0]


def rector_overview(session: Session) -> RectorOverview:
    active_students = int(
        _scalar(
            session,
            """
            SELECT COUNT(DISTINCT student_profile_id)
            FROM enrollments
            WHERE status = 'ACTIVE'
            """,
        )
        or 0
    )
    active_sections = int(
        _scalar(session, "SELECT COUNT(*) FROM sections WHERE status = 'ACTIVE'") or 0
    )

    attendance = session.exec(
        text(
            """
            SELECT
                COUNT(ar.id) AS total,
                COALESCE(SUM(CASE WHEN ac.counts_as_present THEN 1 ELSE 0 END), 0) AS present,
                COALESCE(SUM(CASE WHEN ac.counts_as_absent THEN 1 ELSE 0 END), 0) AS absent,
                COALESCE(SUM(CASE WHEN ac.counts_as_late THEN 1 ELSE 0 END), 0) AS late
            FROM attendance_records ar
            JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
            """
        )
    ).first()

    total = int(attendance[0] or 0)
    present = int(attendance[1] or 0)
    absent = int(attendance[2] or 0)
    late = int(attendance[3] or 0)

    grade_stats = session.exec(
        text(
            """
            SELECT
                AVG((ge.score / NULLIF(a.max_score, 0)) * 100.0)
                    FILTER (WHERE ge.status = 'GRADED' AND ge.score IS NOT NULL),
                COUNT(*) FILTER (WHERE ge.status = 'MISSING')
            FROM grade_entries ge
            JOIN assessments a ON a.id = ge.assessment_id
            """
        )
    ).first()

    average = float(grade_stats[0]) if grade_stats and grade_stats[0] is not None else None
    missing = int(grade_stats[1] or 0) if grade_stats else 0

    open_signals = int(
        _scalar(
            session,
            "SELECT COUNT(*) FROM intelligence_signals WHERE status = 'OPEN'",
        )
        or 0
    )

    def pct(value: int) -> float | None:
        return round((value / total) * 100.0, 2) if total else None

    return RectorOverview(
        active_students=active_students,
        active_sections=active_sections,
        attendance_rate=pct(present),
        absence_rate=pct(absent),
        late_rate=pct(late),
        academic_average_percent=round(average, 2) if average is not None else None,
        missing_grade_entries=missing,
        open_signals=open_signals,
    )


def section_drilldown(session: Session) -> list[SectionIntelligence]:
    rows = session.exec(
        text(
            """
            SELECT
                s.id AS section_id,
                s.name AS section_name,
                g.name AS grade_name,
                COUNT(DISTINCT ssa.id) FILTER (WHERE ssa.status = 'ACTIVE') AS students,
                (
                    SELECT AVG(CASE WHEN ac2.counts_as_present THEN 100.0 ELSE 0.0 END)
                    FROM attendance_records ar2
                    JOIN attendance_codes ac2 ON ac2.id = ar2.attendance_code_id
                    WHERE ar2.section_id = s.id
                ) AS attendance_rate,
                (
                    SELECT AVG((ge2.score / NULLIF(a2.max_score, 0)) * 100.0)
                    FROM grade_entries ge2
                    JOIN assessments a2 ON a2.id = ge2.assessment_id
                    WHERE ge2.section_id = s.id
                      AND ge2.status = 'GRADED'
                      AND ge2.score IS NOT NULL
                ) AS academic_average,
                (
                    SELECT COUNT(*)
                    FROM intelligence_signals sig
                    WHERE sig.section_id = s.id AND sig.status = 'OPEN'
                ) AS open_signals
            FROM sections s
            JOIN grade_levels g ON g.id = s.grade_level_id
            LEFT JOIN student_section_assignments ssa ON ssa.section_id = s.id
            WHERE s.status = 'ACTIVE'
            GROUP BY s.id, s.name, g.name
            ORDER BY g.name, s.name
            """
        )
    ).all()

    return [
        SectionIntelligence(
            section_id=row[0],
            section_name=row[1],
            grade_name=row[2],
            student_count=int(row[3] or 0),
            attendance_rate=round(float(row[4]), 2) if row[4] is not None else None,
            academic_average_percent=round(float(row[5]), 2) if row[5] is not None else None,
            open_signals=int(row[6] or 0),
        )
        for row in rows
    ]


def attendance_trend(session: Session, days: int = 30) -> list[AttendanceTrendPoint]:
    rows = session.exec(
        text(
            """
            SELECT
                cs.session_date,
                COUNT(ar.id) AS total,
                AVG(CASE WHEN ac.counts_as_present THEN 100.0 ELSE 0.0 END) AS present_rate,
                AVG(CASE WHEN ac.counts_as_absent THEN 100.0 ELSE 0.0 END) AS absent_rate,
                AVG(CASE WHEN ac.counts_as_late THEN 100.0 ELSE 0.0 END) AS late_rate
            FROM class_sessions cs
            JOIN attendance_records ar ON ar.class_session_id = cs.id
            JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
            WHERE cs.session_date >= CURRENT_DATE - (:days * INTERVAL '1 day')
            GROUP BY cs.session_date
            ORDER BY cs.session_date
            """
        ).bindparams(days=days)
    ).all()

    return [
        AttendanceTrendPoint(
            day=row[0],
            total_records=int(row[1] or 0),
            attendance_rate=round(float(row[2]), 2) if row[2] is not None else None,
            absence_rate=round(float(row[3]), 2) if row[3] is not None else None,
            late_rate=round(float(row[4]), 2) if row[4] is not None else None,
        )
        for row in rows
    ]


def academic_trend(session: Session) -> list[AcademicTrendPoint]:
    rows = session.exec(
        text(
            """
            SELECT
                gp.id,
                gp.name,
                AVG((ge.score / NULLIF(a.max_score, 0)) * 100.0)
                    FILTER (WHERE ge.status = 'GRADED' AND ge.score IS NOT NULL) AS avg_pct,
                COUNT(ge.id) FILTER (WHERE ge.status = 'GRADED') AS graded,
                COUNT(ge.id) FILTER (WHERE ge.status = 'MISSING') AS missing
            FROM grading_periods gp
            LEFT JOIN assessments a ON a.grading_period_id = gp.id
            LEFT JOIN grade_entries ge ON ge.assessment_id = a.id
            GROUP BY gp.id, gp.name, gp.sequence
            ORDER BY gp.sequence, gp.name
            """
        )
    ).all()

    return [
        AcademicTrendPoint(
            grading_period_id=row[0],
            grading_period_name=row[1],
            average_percent=round(float(row[2]), 2) if row[2] is not None else None,
            graded_entries=int(row[3] or 0),
            missing_entries=int(row[4] or 0),
        )
        for row in rows
    ]


def list_signals(session: Session, status: str = "OPEN") -> list[IntelligenceSignal]:
    return list(
        session.exec(
            select(IntelligenceSignal)
            .where(IntelligenceSignal.status == status)
            .order_by(
                IntelligenceSignal.severity.desc(),
                IntelligenceSignal.last_seen_at.desc(),
            )
        ).all()
    )


def _severity(signal_type: str, metric: float, threshold: float) -> str:
    if signal_type == "ACADEMIC_RISK":
        return "HIGH" if metric < 50.0 else "MEDIUM"
    if signal_type == "ATTENDANCE_RISK":
        return "HIGH" if metric >= 35.0 else "MEDIUM"
    if metric >= threshold * 2:
        return "HIGH"
    return "MEDIUM"


def _upsert_signal(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
    academic_period_id: UUID | None,
    section_id: UUID | None,
    signal_type: str,
    metric_value: float,
    threshold_value: float,
    summary: str,
) -> None:
    now = datetime.now(UTC)
    existing = session.exec(
        select(IntelligenceSignal).where(
            IntelligenceSignal.student_profile_id == student_profile_id,
            IntelligenceSignal.academic_period_id == academic_period_id,
            IntelligenceSignal.signal_type == signal_type,
            IntelligenceSignal.status == "OPEN",
        )
    ).first()

    if existing:
        existing.section_id = section_id
        existing.metric_value = metric_value
        existing.threshold_value = threshold_value
        existing.summary = summary
        existing.severity = _severity(signal_type, metric_value, threshold_value)
        existing.last_seen_at = now
        session.add(existing)
        return

    signal = IntelligenceSignal(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        academic_period_id=academic_period_id,
        section_id=section_id,
        student_profile_id=student_profile_id,
        signal_type=signal_type,
        severity=_severity(signal_type, metric_value, threshold_value),
        metric_value=metric_value,
        threshold_value=threshold_value,
        summary=summary,
        status="OPEN",
        detected_at=now,
        last_seen_at=now,
    )
    session.add(signal)
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.signal.opened",
        event_version=1,
        aggregate_type="intelligence_signal",
        aggregate_id=signal.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(signal.student_profile_id),
            "academic_period_id": (
                str(signal.academic_period_id)
                if signal.academic_period_id is not None
                else None
            ),
            "section_id": (
                str(signal.section_id) if signal.section_id is not None else None
            ),
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "metric_value": float(signal.metric_value),
            "threshold_value": float(signal.threshold_value),
            "summary": signal.summary,
        },
    )

def refresh_signals(
    session: Session,
    principal: CurrentPrincipal,
) -> SignalRefreshResult:
    now = datetime.now(UTC)
    touched: set[tuple[UUID, UUID | None, str]] = set()

    attendance_rows = session.exec(
        text(
            """
            SELECT
                e.student_profile_id,
                ssa.academic_period_id,
                ssa.section_id,
                COUNT(ar.id) AS total,
                COUNT(ar.id) FILTER (WHERE ac.counts_as_absent) AS absent_count,
                COUNT(ar.id) FILTER (WHERE ac.counts_as_late) AS late_count
            FROM student_section_assignments ssa
            JOIN enrollments e ON e.id = ssa.enrollment_id
            LEFT JOIN attendance_records ar
                ON ar.student_section_assignment_id = ssa.id
            LEFT JOIN attendance_codes ac
                ON ac.id = ar.attendance_code_id
            WHERE ssa.status = 'ACTIVE'
            GROUP BY e.student_profile_id, ssa.academic_period_id, ssa.section_id
            """
        )
    ).all()

    for student_id, period_id, section_id, total, absent, late in attendance_rows:
        total = int(total or 0)
        absent = int(absent or 0)
        late = int(late or 0)

        if total >= ATTENDANCE_MIN_RECORDS:
            absence_pct = (absent / total) * 100.0 if total else 0.0
            if absence_pct >= ATTENDANCE_ABSENCE_THRESHOLD:
                _upsert_signal(
                    session,
                    principal,
                    student_profile_id=student_id,
                    academic_period_id=period_id,
                    section_id=section_id,
                    signal_type="ATTENDANCE_RISK",
                    metric_value=round(absence_pct, 2),
                    threshold_value=ATTENDANCE_ABSENCE_THRESHOLD,
                    summary=(
                        f"Ausencias {absence_pct:.1f}% sobre {total} registros de asistencia."
                    ),
                )
                touched.add((student_id, period_id, "ATTENDANCE_RISK"))

        if late >= LATE_COUNT_THRESHOLD:
            _upsert_signal(
                session,
                principal,
                student_profile_id=student_id,
                academic_period_id=period_id,
                section_id=section_id,
                signal_type="REPEATED_LATE",
                metric_value=float(late),
                threshold_value=LATE_COUNT_THRESHOLD,
                summary=f"Se registran {late} atrasos en el período.",
            )
            touched.add((student_id, period_id, "REPEATED_LATE"))

    academic_rows = session.exec(
        text(
            """
            SELECT
                e.student_profile_id,
                ssa.academic_period_id,
                ssa.section_id,
                COUNT(ge.id) FILTER (
                    WHERE ge.status = 'GRADED' AND ge.score IS NOT NULL
                ) AS graded_count,
                AVG((ge.score / NULLIF(a.max_score, 0)) * 100.0)
                    FILTER (
                        WHERE ge.status = 'GRADED' AND ge.score IS NOT NULL
                    ) AS avg_pct,
                COUNT(ge.id) FILTER (WHERE ge.status = 'MISSING') AS missing_count
            FROM student_section_assignments ssa
            JOIN enrollments e ON e.id = ssa.enrollment_id
            LEFT JOIN grade_entries ge
                ON ge.student_section_assignment_id = ssa.id
            LEFT JOIN assessments a
                ON a.id = ge.assessment_id
            WHERE ssa.status = 'ACTIVE'
            GROUP BY e.student_profile_id, ssa.academic_period_id, ssa.section_id
            """
        )
    ).all()

    for student_id, period_id, section_id, graded_count, avg_pct, missing_count in academic_rows:
        graded_count = int(graded_count or 0)
        missing_count = int(missing_count or 0)

        if (
            graded_count >= ACADEMIC_MIN_GRADED
            and avg_pct is not None
            and float(avg_pct) < ACADEMIC_AVERAGE_THRESHOLD
        ):
            metric = round(float(avg_pct), 2)
            _upsert_signal(
                session,
                principal,
                student_profile_id=student_id,
                academic_period_id=period_id,
                section_id=section_id,
                signal_type="ACADEMIC_RISK",
                metric_value=metric,
                threshold_value=ACADEMIC_AVERAGE_THRESHOLD,
                summary=(
                    f"Promedio normalizado {metric:.1f}% en "
                    f"{graded_count} evaluaciones calificadas."
                ),
            )
            touched.add((student_id, period_id, "ACADEMIC_RISK"))

        if missing_count >= MISSING_WORK_THRESHOLD:
            _upsert_signal(
                session,
                principal,
                student_profile_id=student_id,
                academic_period_id=period_id,
                section_id=section_id,
                signal_type="MISSING_WORK",
                metric_value=float(missing_count),
                threshold_value=MISSING_WORK_THRESHOLD,
                summary=f"Se registran {missing_count} evaluaciones faltantes.",
            )
            touched.add((student_id, period_id, "MISSING_WORK"))

    open_signals = list(
        session.exec(select(IntelligenceSignal).where(IntelligenceSignal.status == "OPEN")).all()
    )
    auto_closed = 0
    for signal in open_signals:
        key = (signal.student_profile_id, signal.academic_period_id, signal.signal_type)
        if key not in touched:
            signal.status = "CLOSED"
            signal.resolved_at = now
            signal.resolution_note = "Cierre automático: la condición dejó de cumplirse."
            session.add(signal)
            enqueue_canonical_event(
                session,
                institution_id=principal.institution_id,
                event_type="student.signal.closed",
                event_version=1,
                aggregate_type="intelligence_signal",
                aggregate_id=signal.id,
                actor_user_id=principal.user_id,
                payload={
                    "student_profile_id": str(signal.student_profile_id),
                    "academic_period_id": (
                        str(signal.academic_period_id)
                        if signal.academic_period_id is not None
                        else None
                    ),
                    "section_id": (
                        str(signal.section_id)
                        if signal.section_id is not None
                        else None
                    ),
                    "signal_type": signal.signal_type,
                    "severity": signal.severity,
                    "closure_type": "AUTO",
                    "resolution_note": signal.resolution_note,
                },
            )
            auto_closed += 1

    session.commit()
    return SignalRefreshResult(
        detected_or_refreshed=len(touched),
        auto_closed=auto_closed,
    )


def resolve_signal(
    session: Session,
    principal: CurrentPrincipal,
    signal_id: UUID,
    payload: SignalResolve,
) -> IntelligenceSignal:
    signal = session.get(IntelligenceSignal, signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.status != "OPEN":
        raise HTTPException(status_code=409, detail="Signal is not open")

    signal.status = "RESOLVED"
    signal.resolved_at = datetime.now(UTC)
    signal.resolution_note = payload.resolution_note
    session.add(signal)
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.signal.resolved",
        event_version=1,
        aggregate_type="intelligence_signal",
        aggregate_id=signal.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(signal.student_profile_id),
            "academic_period_id": (
                str(signal.academic_period_id)
                if signal.academic_period_id is not None
                else None
            ),
            "section_id": (
                str(signal.section_id) if signal.section_id is not None else None
            ),
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "closure_type": "HUMAN",
            "resolution_note": signal.resolution_note,
        },
    )
    session.commit()
    session.refresh(signal)
    return signal
