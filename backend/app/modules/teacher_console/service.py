from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import TeacherPrincipal
from app.modules.attendance.schemas import (
    AttendanceRecordUpsert,
    ClassSessionCreate,
)
from app.modules.attendance.service import (
    apply_attendance_record,
    create_session,
)
from app.modules.audit.models import AuditLog
from app.modules.automation.schemas import TaskComplete
from app.modules.automation.service import acknowledge_task, complete_task
from app.modules.grades.schemas import (
    AssessmentCategoryCreate,
    AssessmentCreate,
    AssessmentStatusChange,
    GradeEntryUpsert,
)
from app.modules.grades.service import (
    change_assessment_status,
    create_assessment,
    create_category,
    upsert_entry,
)
from app.modules.grades.service import (
    grade_entry_history as get_grade_entry_history,
)
from app.modules.teacher_console.schemas import (
    TeacherAlert,
    TeacherAssessmentCreate,
    TeacherAssessmentRead,
    TeacherAssessmentStatusChange,
    TeacherAttendanceCode,
    TeacherAttendanceCommand,
    TeacherAttendanceRow,
    TeacherCategoryCreate,
    TeacherCategoryRead,
    TeacherClassRead,
    TeacherClassSession,
    TeacherGradeMark,
    TeacherGradeRow,
    TeacherGradingPeriod,
    TeacherRosterStudent,
    TeacherSessionCreate,
    TeacherSummary,
    TeacherTaskComplete,
    TeacherTaskRead,
)


def _audit(
    session: Session,
    principal: TeacherPrincipal,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata or {},
        )
    )


def _offering_scope(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT
                co.id,
                co.section_id,
                co.academic_period_id
            FROM course_offerings co
            JOIN teaching_assignments ta
              ON ta.course_offering_id = co.id
             AND ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
             AND ta.organization_id = CAST(:organization_id AS uuid)
             AND ta.institution_id = CAST(:institution_id AS uuid)
            WHERE co.id = CAST(:course_offering_id AS uuid)
              AND co.organization_id = CAST(:organization_id AS uuid)
              AND co.institution_id = CAST(:institution_id AS uuid)
              AND co.status = 'ACTIVE'
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            LIMIT 1
            """
        ).bindparams(
                staff_profile_id=str(principal.staff_profile_id),
                course_offering_id=str(course_offering_id),
                organization_id=str(principal.organization_id),
                institution_id=str(principal.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=403,
            detail="Course offering is not assigned to the current teacher",
        )
    return row


def _section_in_scope(
    session: Session,
    principal: TeacherPrincipal,
    section_id: UUID | None,
) -> bool:
    if section_id is None:
        return False
    row = session.exec(
        text(
            """
            SELECT 1
            FROM teaching_assignments ta
            JOIN course_offerings co ON co.id = ta.course_offering_id
            WHERE ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
              AND co.section_id = CAST(:section_id AS uuid)
              AND co.status = 'ACTIVE'
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            LIMIT 1
            """
        ).bindparams(
            staff_profile_id=str(principal.staff_profile_id),
            section_id=str(section_id),
        )
    ).first()
    return row is not None


def teacher_summary(
    session: Session,
    principal: TeacherPrincipal,
) -> TeacherSummary:
    row = session.exec(
        text(
            """
            WITH scoped AS (
                SELECT DISTINCT co.id, co.section_id, co.academic_period_id
                FROM teaching_assignments ta
                JOIN course_offerings co ON co.id = ta.course_offering_id
                JOIN academic_periods ap ON ap.id=co.academic_period_id AND ap.status='ACTIVE'
                WHERE ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
                  AND co.status = 'ACTIVE'
                  AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
                  AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            ),
            scoped_students AS (
                SELECT DISTINCT e.student_profile_id
                FROM scoped s
                JOIN student_section_assignments ssa
                  ON ssa.section_id = s.section_id
                 AND ssa.academic_period_id = s.academic_period_id
                 AND ssa.status IN ('ACTIVE', 'TRANSFERRED')
                 AND ssa.assigned_on <= CURRENT_DATE
                 AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)
                JOIN enrollments e ON e.id = ssa.enrollment_id
                JOIN student_profiles sp ON sp.id = e.student_profile_id
                  AND sp.status = 'ACTIVE'
                JOIN sections sec ON sec.id = ssa.section_id
                  AND sec.academic_period_id = ssa.academic_period_id
                  AND sec.campus_id = e.campus_id AND sec.status = 'ACTIVE'
                JOIN academic_periods ap ON ap.id = ssa.academic_period_id
                  AND ap.status = 'ACTIVE'
                WHERE e.status = 'ACTIVE'
            )
            SELECT
                (SELECT COUNT(*) FROM scoped),
                (SELECT COUNT(DISTINCT section_id) FROM scoped),
                (SELECT COUNT(*) FROM scoped_students),
                (
                    SELECT COUNT(*)
                    FROM class_sessions cs
                    JOIN scoped s ON s.id = cs.course_offering_id
                    WHERE cs.session_date = CURRENT_DATE
                ),
                (
                    SELECT COUNT(*)
                    FROM intelligence_signals sig
                    WHERE sig.status = 'OPEN'
                      AND sig.section_id IN (
                          SELECT section_id FROM scoped
                      )
                ),
                (
                    SELECT COUNT(*)
                    FROM automation_tasks t
                    JOIN automation_cases c ON c.id = t.automation_case_id
                    WHERE t.assigned_role_code = 'TEACHER'
                      AND t.status IN ('OPEN', 'ACKNOWLEDGED', 'ESCALATED')
                      AND c.section_id IN (
                          SELECT section_id FROM scoped
                      )
                ),
                (
                    SELECT COUNT(*)
                    FROM automation_tasks t
                    JOIN automation_cases c ON c.id = t.automation_case_id
                    WHERE t.assigned_role_code = 'TEACHER'
                      AND t.status = 'ESCALATED'
                      AND c.section_id IN (
                          SELECT section_id FROM scoped
                      )
                ),
                (
                    SELECT COUNT(*)
                    FROM grade_entries ge
                    JOIN assessments a ON a.id = ge.assessment_id
                    WHERE ge.status = 'MISSING'
                      AND a.course_offering_id IN (
                          SELECT id FROM scoped
                      )
                )
            """
        ).bindparams(staff_profile_id=str(principal.staff_profile_id))
    ).first()

    assert row is not None
    return TeacherSummary(
        assigned_classes=int(row[0] or 0),
        assigned_sections=int(row[1] or 0),
        unique_students=int(row[2] or 0),
        today_sessions=int(row[3] or 0),
        relevant_open_signals=int(row[4] or 0),
        open_teacher_tasks=int(row[5] or 0),
        escalated_teacher_tasks=int(row[6] or 0),
        missing_grade_entries=int(row[7] or 0),
    )


def list_teacher_classes(
    session: Session,
    principal: TeacherPrincipal,
) -> list[TeacherClassRead]:
    rows = session.exec(
        text(
            """
            SELECT
                co.id,
                co.academic_period_id,
                ap.name,
                co.section_id,
                sec.name,
                gl.name,
                sub.id,
                sub.code,
                sub.name,
                ta.assignment_role,
                COUNT(DISTINCT ssa.id) FILTER (
                    WHERE ssa.status IN ('ACTIVE', 'TRANSFERRED')
                      AND ssa.assigned_on <= CURRENT_DATE
                      AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)
                      AND roster_enrollment.id IS NOT NULL
                      AND roster_student.id IS NOT NULL
                      AND roster_enrollment.campus_id = sec.campus_id
                )
            FROM teaching_assignments ta
            JOIN course_offerings co ON co.id = ta.course_offering_id
            JOIN academic_periods ap ON ap.id = co.academic_period_id
            JOIN sections sec ON sec.id = co.section_id
            JOIN grade_levels gl ON gl.id = sec.grade_level_id
            JOIN subjects sub ON sub.id = co.subject_id
            LEFT JOIN student_section_assignments ssa
              ON ssa.section_id = co.section_id
             AND ssa.academic_period_id = co.academic_period_id
            LEFT JOIN enrollments roster_enrollment
              ON roster_enrollment.id = ssa.enrollment_id
             AND roster_enrollment.status = 'ACTIVE'
            LEFT JOIN student_profiles roster_student
              ON roster_student.id = roster_enrollment.student_profile_id
             AND roster_student.status = 'ACTIVE'
            WHERE ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
              AND co.status = 'ACTIVE'
              AND ap.status = 'ACTIVE'
              AND sec.status = 'ACTIVE'
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            GROUP BY
                co.id,
                co.academic_period_id,
                ap.name,
                co.section_id,
                sec.name,
                gl.name,
                sub.id,
                sub.code,
                sub.name,
                ta.assignment_role
            ORDER BY gl.name, sec.name, sub.name
            """
        ).bindparams(staff_profile_id=str(principal.staff_profile_id))
    ).all()

    return [
        TeacherClassRead(
            course_offering_id=row[0],
            academic_period_id=row[1],
            academic_period_name=row[2],
            section_id=row[3],
            section_name=row[4],
            grade_name=row[5],
            subject_id=row[6],
            subject_code=row[7],
            subject_name=row[8],
            assignment_role=row[9],
            student_count=int(row[10] or 0),
        )
        for row in rows
    ]


def list_roster(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
) -> list[TeacherRosterStudent]:
    scope = _offering_scope(
        session,
        principal,
        course_offering_id,
    )
    rows = session.exec(
        text(
            """
            SELECT
                ssa.id,
                sp.id,
                sp.student_code,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                e.enrollment_number
            FROM student_section_assignments ssa
            JOIN enrollments e ON e.id = ssa.enrollment_id
            JOIN student_profiles sp ON sp.id = e.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            JOIN sections sec ON sec.id = ssa.section_id
              AND sec.academic_period_id = ssa.academic_period_id
            JOIN academic_periods ap ON ap.id = ssa.academic_period_id
            WHERE ssa.section_id = CAST(:section_id AS uuid)
              AND ssa.organization_id = CAST(:organization_id AS uuid)
              AND ssa.institution_id = CAST(:institution_id AS uuid)
              AND ssa.status IN ('ACTIVE', 'TRANSFERRED')
              AND ssa.assigned_on <= CURRENT_DATE
              AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)
              AND ssa.academic_period_id = sec.academic_period_id
              AND e.status = 'ACTIVE'
              AND sp.status = 'ACTIVE'
              AND e.campus_id = sec.campus_id
              AND e.organization_id = CAST(:organization_id AS uuid)
              AND e.institution_id = CAST(:institution_id AS uuid)
              AND sp.organization_id = CAST(:organization_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sec.status = 'ACTIVE'
              AND ap.status = 'ACTIVE'
            ORDER BY p.family_names, p.given_names
            """
        ).bindparams(
            section_id=str(scope[1]),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).all()
    return [
        TeacherRosterStudent(
            student_section_assignment_id=row[0],
            student_profile_id=row[1],
            student_code=row[2],
            student_name=row[3],
            enrollment_number=row[4],
        )
        for row in rows
    ]


def list_attendance_codes(
    session: Session, principal: TeacherPrincipal
) -> list[TeacherAttendanceCode]:
    rows = session.exec(
        text(
            """
            SELECT
                id,
                code,
                label,
                semantic,
                counts_as_present,
                counts_as_absent,
                counts_as_late
            FROM attendance_codes
            WHERE status = 'ACTIVE'
              AND organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            ORDER BY code
            """
        ).bindparams(
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).all()
    return [
        TeacherAttendanceCode(
            id=row[0],
            code=row[1],
            label=row[2],
            semantic=row[3],
            counts_as_present=bool(row[4]),
            counts_as_absent=bool(row[5]),
            counts_as_late=bool(row[6]),
        )
        for row in rows
    ]


def list_class_sessions(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
) -> list[TeacherClassSession]:
    _offering_scope(session, principal, course_offering_id)
    rows = session.exec(
        text(
            """
            SELECT
                id,
                course_offering_id,
                section_id,
                session_date,
                starts_at,
                ends_at,
                status
            FROM class_sessions
            WHERE course_offering_id = CAST(:course_offering_id AS uuid)
              AND organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
            ORDER BY session_date DESC, starts_at DESC
            """
        ).bindparams(
            course_offering_id=str(course_offering_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).all()
    return [
        TeacherClassSession(
            id=row[0],
            course_offering_id=row[1],
            section_id=row[2],
            session_date=row[3],
            starts_at=row[4],
            ends_at=row[5],
            status=row[6],
        )
        for row in rows
    ]


def create_teacher_session(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
    payload: TeacherSessionCreate,
) -> TeacherClassSession:
    _offering_scope(session, principal, course_offering_id)
    entity = create_session(
        session,
        principal,
        ClassSessionCreate(
            course_offering_id=course_offering_id,
            schedule_slot_id=payload.schedule_slot_id,
            session_date=payload.session_date,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        ),
    )
    _audit(
        session,
        principal,
        "TEACHER_SESSION_CREATED",
        "ClassSession",
        entity.id,
        {"course_offering_id": str(course_offering_id)},
    )
    session.commit()
    return TeacherClassSession(
        id=entity.id,
        course_offering_id=entity.course_offering_id,
        section_id=entity.section_id,
        session_date=entity.session_date,
        starts_at=entity.starts_at,
        ends_at=entity.ends_at,
        status=entity.status,
    )


def _session_scope(
    session: Session,
    principal: TeacherPrincipal,
    class_session_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT cs.id, cs.course_offering_id, cs.section_id,
                   cs.session_date, co.academic_period_id
            FROM class_sessions cs
            JOIN teaching_assignments ta
              ON ta.course_offering_id = cs.course_offering_id
             AND ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
             AND ta.organization_id = CAST(:organization_id AS uuid)
             AND ta.institution_id = CAST(:institution_id AS uuid)
            JOIN course_offerings co
              ON co.id = cs.course_offering_id
             AND co.organization_id = CAST(:organization_id AS uuid)
             AND co.institution_id = CAST(:institution_id AS uuid)
             AND co.status = 'ACTIVE'
            JOIN academic_periods ap
              ON ap.id = co.academic_period_id
             AND ap.organization_id = CAST(:organization_id AS uuid)
             AND ap.institution_id = CAST(:institution_id AS uuid)
             AND ap.status = 'ACTIVE'
             AND cs.session_date BETWEEN ap.starts_on AND ap.ends_on
            WHERE cs.id = CAST(:class_session_id AS uuid)
              AND cs.organization_id = CAST(:organization_id AS uuid)
              AND cs.institution_id = CAST(:institution_id AS uuid)
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
              AND (ta.starts_on IS NULL OR ta.starts_on <= cs.session_date)
              AND (ta.ends_on IS NULL OR ta.ends_on >= cs.session_date)
            LIMIT 1
            """
        ).bindparams(
            staff_profile_id=str(principal.staff_profile_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            class_session_id=str(class_session_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=403,
            detail="Class session is outside the current teacher scope",
        )
    return row


def attendance_rows(
    session: Session,
    principal: TeacherPrincipal,
    class_session_id: UUID,
) -> list[TeacherAttendanceRow]:
    scoped = _session_scope(session, principal, class_session_id)
    rows = session.exec(
        text(
            """
            SELECT
                ssa.id,
                sp.id,
                sp.student_code,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                ar.id,
                ar.attendance_code_id,
                ac.code,
                ac.label,
                COALESCE(ar.minutes_late, 0),
                ar.note
            FROM student_section_assignments ssa
            JOIN enrollments e ON e.id = ssa.enrollment_id
             AND e.organization_id = CAST(:organization_id AS uuid)
             AND e.institution_id = CAST(:institution_id AS uuid)
            JOIN student_profiles sp ON sp.id = e.student_profile_id
             AND sp.organization_id = CAST(:organization_id AS uuid)
             AND sp.institution_id = CAST(:institution_id AS uuid)
            JOIN persons p ON p.id = sp.person_id
             AND p.organization_id = CAST(:organization_id AS uuid)
            LEFT JOIN attendance_records ar
              ON ar.class_session_id = CAST(:class_session_id AS uuid)
             AND ar.student_section_assignment_id = ssa.id
             AND ar.organization_id = CAST(:organization_id AS uuid)
             AND ar.institution_id = CAST(:institution_id AS uuid)
            LEFT JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
             AND ac.organization_id = CAST(:organization_id AS uuid)
             AND ac.institution_id = CAST(:institution_id AS uuid)
            JOIN class_sessions cs ON cs.id = CAST(:class_session_id AS uuid)
             AND cs.organization_id = CAST(:organization_id AS uuid)
             AND cs.institution_id = CAST(:institution_id AS uuid)
            JOIN sections sec ON sec.id = ssa.section_id
             AND sec.organization_id = CAST(:organization_id AS uuid)
             AND sec.institution_id = CAST(:institution_id AS uuid)
             AND sec.academic_period_id = ssa.academic_period_id
            WHERE ssa.section_id = CAST(:section_id AS uuid)
              AND ssa.institution_id = CAST(:institution_id AS uuid)
              AND ssa.status IN ('ACTIVE', 'TRANSFERRED')
              AND ssa.assigned_on <= cs.session_date
              AND (ssa.ended_on IS NULL OR ssa.ended_on >= cs.session_date)
              AND e.status = 'ACTIVE'
              AND sp.status = 'ACTIVE'
              AND e.campus_id = sec.campus_id
              AND ssa.academic_period_id = CAST(:period_id AS uuid)
              AND sec.status = 'ACTIVE'
            ORDER BY p.family_names, p.given_names
            """
        ).bindparams(
            class_session_id=str(class_session_id),
            section_id=str(scoped[2]),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            period_id=str(scoped[4]),
        )
    ).all()
    return [
        TeacherAttendanceRow(
            student_section_assignment_id=row[0],
            student_profile_id=row[1],
            student_code=row[2],
            student_name=row[3],
            attendance_record_id=row[4],
            attendance_code_id=row[5],
            attendance_code=row[6],
            attendance_label=row[7],
            minutes_late=int(row[8] or 0),
            note=row[9],
        )
        for row in rows
    ]


def mark_attendance(
    session: Session,
    principal: TeacherPrincipal,
    class_session_id: UUID,
    payload: TeacherAttendanceCommand,
):
    mutation = apply_attendance_record(
        session,
        principal,
        class_session_id,
        AttendanceRecordUpsert(
            student_section_assignment_id=payload.student_section_assignment_id,
            attendance_code_id=payload.attendance_code_id,
            minutes_late=payload.minutes_late,
            note=payload.note,
            expected_state=payload.expected_state,
            correction_reason=payload.correction_reason,
        ),
        expected_state=payload.expected_state,
        correction_reason=payload.correction_reason,
        source="teacher_m10",
        teacher_scope_required=True,
        commit=False,
    )
    session.commit()
    return mutation.record


def grading_periods(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
) -> list[TeacherGradingPeriod]:
    scope = _offering_scope(session, principal, course_offering_id)
    rows = session.exec(
        text(
            """
            SELECT
                id,
                academic_period_id,
                code,
                name,
                starts_on,
                ends_on,
                sequence,
                status
            FROM grading_periods
            WHERE academic_period_id = CAST(:academic_period_id AS uuid)
            ORDER BY sequence, starts_on
            """
        ).bindparams(academic_period_id=str(scope[2]))
    ).all()
    return [
        TeacherGradingPeriod(
            id=row[0],
            academic_period_id=row[1],
            code=row[2],
            name=row[3],
            starts_on=row[4],
            ends_on=row[5],
            sequence=int(row[6]),
            status=row[7],
        )
        for row in rows
    ]


def list_categories(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
) -> list[TeacherCategoryRead]:
    _offering_scope(session, principal, course_offering_id)
    rows = session.exec(
        text(
            """
            SELECT
                id,
                course_offering_id,
                grading_period_id,
                code,
                name,
                weight_percent
            FROM assessment_categories
            WHERE course_offering_id = CAST(:course_offering_id AS uuid)
            ORDER BY created_at
            """
        ).bindparams(course_offering_id=str(course_offering_id))
    ).all()
    return [
        TeacherCategoryRead(
            id=row[0],
            course_offering_id=row[1],
            grading_period_id=row[2],
            code=row[3],
            name=row[4],
            weight_percent=float(row[5]),
        )
        for row in rows
    ]


def _assert_period_for_offering(
    session: Session,
    academic_period_id: UUID,
    grading_period_id: UUID,
) -> None:
    row = session.exec(
        text(
            """
            SELECT 1
            FROM grading_periods
            WHERE id = CAST(:grading_period_id AS uuid)
              AND academic_period_id = CAST(:academic_period_id AS uuid)
            LIMIT 1
            """
        ).bindparams(
            grading_period_id=str(grading_period_id),
            academic_period_id=str(academic_period_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="Grading period does not belong to the class academic period",
        )


def create_teacher_category(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
    payload: TeacherCategoryCreate,
) -> TeacherCategoryRead:
    scope = _offering_scope(session, principal, course_offering_id)
    _assert_period_for_offering(
        session,
        scope[2],
        payload.grading_period_id,
    )
    entity = create_category(
        session,
        principal,
        AssessmentCategoryCreate(
            course_offering_id=course_offering_id,
            **payload.model_dump(),
        ),
    )
    return TeacherCategoryRead(
        id=entity.id,
        course_offering_id=entity.course_offering_id,
        grading_period_id=entity.grading_period_id,
        code=entity.code,
        name=entity.name,
        weight_percent=entity.weight_percent,
    )


def list_assessments(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
) -> list[TeacherAssessmentRead]:
    _offering_scope(session, principal, course_offering_id)
    rows = session.exec(
        text(
            """
            SELECT
                id,
                course_offering_id,
                section_id,
                grading_period_id,
                assessment_category_id,
                code,
                title,
                max_score,
                due_on,
                status
            FROM assessments
            WHERE course_offering_id = CAST(:course_offering_id AS uuid)
            ORDER BY created_at DESC
            """
        ).bindparams(course_offering_id=str(course_offering_id))
    ).all()
    return [
        TeacherAssessmentRead(
            id=row[0],
            course_offering_id=row[1],
            section_id=row[2],
            grading_period_id=row[3],
            assessment_category_id=row[4],
            code=row[5],
            title=row[6],
            max_score=float(row[7]),
            due_on=row[8],
            status=row[9],
        )
        for row in rows
    ]


def create_teacher_assessment(
    session: Session,
    principal: TeacherPrincipal,
    course_offering_id: UUID,
    payload: TeacherAssessmentCreate,
) -> TeacherAssessmentRead:
    scope = _offering_scope(session, principal, course_offering_id)
    _assert_period_for_offering(
        session,
        scope[2],
        payload.grading_period_id,
    )
    category = session.exec(
        text(
            """
            SELECT 1
            FROM assessment_categories
            WHERE id = CAST(:category_id AS uuid)
              AND course_offering_id = CAST(:course_offering_id AS uuid)
              AND grading_period_id = CAST(:grading_period_id AS uuid)
            LIMIT 1
            """
        ).bindparams(
            category_id=str(payload.assessment_category_id),
            course_offering_id=str(course_offering_id),
            grading_period_id=str(payload.grading_period_id),
        )
    ).first()
    if category is None:
        raise HTTPException(
            status_code=409,
            detail="Assessment category is outside the selected class or period",
        )

    entity = create_assessment(
        session,
        principal,
        AssessmentCreate(
            course_offering_id=course_offering_id,
            **payload.model_dump(),
        ),
    )
    return TeacherAssessmentRead(
        id=entity.id,
        course_offering_id=entity.course_offering_id,
        section_id=entity.section_id,
        grading_period_id=entity.grading_period_id,
        assessment_category_id=entity.assessment_category_id,
        code=entity.code,
        title=entity.title,
        max_score=entity.max_score,
        due_on=entity.due_on,
        status=entity.status,
    )


def _assessment_scope(
    session: Session,
    principal: TeacherPrincipal,
    assessment_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT a.id, a.course_offering_id, a.section_id, a.max_score,
                   a.status, a.due_on, a.grading_period_id
            FROM assessments a
            JOIN teaching_assignments ta
              ON ta.course_offering_id = a.course_offering_id
             AND ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
             AND ta.organization_id = CAST(:organization_id AS uuid)
             AND ta.institution_id = CAST(:institution_id AS uuid)
            JOIN course_offerings co ON co.id=a.course_offering_id
             AND co.organization_id=CAST(:organization_id AS uuid)
             AND co.institution_id=CAST(:institution_id AS uuid)
             AND co.status='ACTIVE'
            JOIN academic_periods ap ON ap.id=co.academic_period_id
             AND ap.status='ACTIVE'
            WHERE a.id = CAST(:assessment_id AS uuid)
              AND a.organization_id = CAST(:organization_id AS uuid)
              AND a.institution_id = CAST(:institution_id AS uuid)
              AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
              AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            LIMIT 1
            """
        ).bindparams(
            staff_profile_id=str(principal.staff_profile_id),
            assessment_id=str(assessment_id),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=403,
            detail="Assessment is outside the current teacher scope",
        )
    return row


def grade_rows(
    session: Session,
    principal: TeacherPrincipal,
    assessment_id: UUID,
) -> list[TeacherGradeRow]:
    scope = _assessment_scope(session, principal, assessment_id)
    rows = session.exec(
        text(
            """
            SELECT
                ssa.id,
                sp.id,
                sp.student_code,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                ge.id,
                ge.score,
                COALESCE(ge.status, 'PENDING'),
                ge.feedback
                ,COALESCE((SELECT MAX((al.metadata_json->>'result_revision')::integer)
                    FROM audit_logs al
                    WHERE al.institution_id=CAST(:institution_id AS uuid)
                      AND al.entity_type='GradeEntry' AND al.entity_id=ge.id
                      AND al.action IN ('GRADE_RESULT_RECORDED','GRADE_RESULT_CORRECTED')
                      AND al.metadata_json ? 'result_revision'),0) AS result_revision
            FROM student_section_assignments ssa
            JOIN enrollments e ON e.id = ssa.enrollment_id
            JOIN student_profiles sp ON sp.id = e.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN grade_entries ge
              ON ge.assessment_id = CAST(:assessment_id AS uuid)
             AND ge.student_section_assignment_id = ssa.id
            WHERE ssa.section_id = CAST(:section_id AS uuid)
              AND ssa.status = 'ACTIVE'
              AND ssa.organization_id = CAST(:organization_id AS uuid)
              AND ssa.institution_id = CAST(:institution_id AS uuid)
              AND ssa.academic_period_id = (SELECT academic_period_id FROM course_offerings WHERE id=CAST(:course_offering_id AS uuid))
              AND ssa.assigned_on <= CURRENT_DATE
              AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)
              AND e.organization_id = CAST(:organization_id AS uuid)
              AND e.institution_id = CAST(:institution_id AS uuid)
              AND e.academic_period_id = ssa.academic_period_id
              AND e.status = 'ACTIVE'
              AND sp.organization_id = CAST(:organization_id AS uuid)
              AND sp.institution_id = CAST(:institution_id AS uuid)
              AND sp.status = 'ACTIVE'
            ORDER BY p.family_names, p.given_names
            """
        ).bindparams(
            assessment_id=str(assessment_id),
            section_id=str(scope[2]),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
            course_offering_id=str(scope[1]),
        )
    ).all()
    return [
        TeacherGradeRow(
            student_section_assignment_id=row[0],
            student_profile_id=row[1],
            student_code=row[2],
            student_name=row[3],
            grade_entry_id=row[4],
            score=float(row[5]) if row[5] is not None else None,
            status=row[6],
            feedback=row[7],
            revision=int(row[8]),
        )
        for row in rows
    ]


def mark_grade(
    session: Session,
    principal: TeacherPrincipal,
    assessment_id: UUID,
    payload: TeacherGradeMark,
):
    scope = _assessment_scope(session, principal, assessment_id)
    belongs = session.exec(
        text(
            """
            SELECT 1
            FROM student_section_assignments
            WHERE id = CAST(:assignment_id AS uuid)
              AND section_id = CAST(:section_id AS uuid)
              AND organization_id = CAST(:organization_id AS uuid)
              AND institution_id = CAST(:institution_id AS uuid)
              AND status = 'ACTIVE'
            LIMIT 1
            """
        ).bindparams(
            assignment_id=str(payload.student_section_assignment_id),
            section_id=str(scope[2]),
            organization_id=str(principal.organization_id),
            institution_id=str(principal.institution_id),
        )
    ).first()
    if belongs is None:
        raise HTTPException(
            status_code=403,
            detail="Student is outside the assessment roster",
        )

    entry = upsert_entry(
        session,
        principal,
        assessment_id,
        GradeEntryUpsert(**payload.model_dump()),
    )
    return entry


def change_teacher_assessment_status(
    session: Session,
    principal: TeacherPrincipal,
    assessment_id: UUID,
    payload: TeacherAssessmentStatusChange,
):
    _assessment_scope(session, principal, assessment_id)
    return change_assessment_status(
        session,
        principal,
        assessment_id,
        AssessmentStatusChange(**payload.model_dump()),
    )


def teacher_grade_history(
    session: Session,
    principal: TeacherPrincipal,
    assessment_id: UUID,
    assignment_id: UUID,
):
    _assessment_scope(session, principal, assessment_id)
    return get_grade_entry_history(session, principal, assessment_id, assignment_id)


def list_teacher_alerts(
    session: Session,
    principal: TeacherPrincipal,
) -> list[TeacherAlert]:
    rows = session.exec(
        text(
            """
            SELECT
                sig.id,
                sig.student_profile_id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                sp.student_code,
                sig.section_id,
                sec.name,
                sig.signal_type,
                sig.severity,
                sig.summary,
                sig.metric_value,
                sig.threshold_value,
                sig.last_seen_at
            FROM intelligence_signals sig
            JOIN student_profiles sp ON sp.id = sig.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN sections sec ON sec.id = sig.section_id
            WHERE sig.status = 'OPEN'
              AND sig.section_id IN (
                  SELECT DISTINCT co.section_id
                  FROM teaching_assignments ta
                  JOIN course_offerings co ON co.id = ta.course_offering_id
                  WHERE ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
                    AND co.status = 'ACTIVE'
                    AND (
                        ta.starts_on IS NULL
                        OR ta.starts_on <= CURRENT_DATE
                    )
                    AND (
                        ta.ends_on IS NULL
                        OR ta.ends_on >= CURRENT_DATE
                    )
              )
            ORDER BY
                CASE sig.severity
                    WHEN 'HIGH' THEN 3
                    WHEN 'MEDIUM' THEN 2
                    ELSE 1
                END DESC,
                sig.last_seen_at DESC
            """
        ).bindparams(staff_profile_id=str(principal.staff_profile_id))
    ).all()
    return [
        TeacherAlert(
            signal_id=row[0],
            student_profile_id=row[1],
            student_name=row[2],
            student_code=row[3],
            section_id=row[4],
            section_name=row[5],
            signal_type=row[6],
            severity=row[7],
            summary=row[8],
            metric_value=float(row[9]),
            threshold_value=float(row[10]),
            last_seen_at=row[11],
        )
        for row in rows
    ]


def list_teacher_tasks(
    session: Session,
    principal: TeacherPrincipal,
) -> list[TeacherTaskRead]:
    rows = session.exec(
        text(
            """
            SELECT
                t.id,
                t.automation_case_id,
                c.student_profile_id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                sp.student_code,
                c.section_id,
                sec.name,
                t.title,
                t.description,
                t.status,
                t.due_at,
                t.escalate_at,
                t.acknowledged_at,
                t.completed_at,
                t.completion_note
            FROM automation_tasks t
            JOIN automation_cases c ON c.id = t.automation_case_id
            JOIN student_profiles sp ON sp.id = c.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN sections sec ON sec.id = c.section_id
            WHERE t.assigned_role_code = 'TEACHER'
              AND c.section_id IN (
                  SELECT DISTINCT co.section_id
                  FROM teaching_assignments ta
                  JOIN course_offerings co ON co.id = ta.course_offering_id
                  WHERE ta.staff_profile_id = CAST(:staff_profile_id AS uuid)
                    AND co.status = 'ACTIVE'
                    AND (
                        ta.starts_on IS NULL
                        OR ta.starts_on <= CURRENT_DATE
                    )
                    AND (
                        ta.ends_on IS NULL
                        OR ta.ends_on >= CURRENT_DATE
                    )
              )
            ORDER BY
                CASE t.status
                    WHEN 'ESCALATED' THEN 4
                    WHEN 'OPEN' THEN 3
                    WHEN 'ACKNOWLEDGED' THEN 2
                    ELSE 1
                END DESC,
                t.due_at
            """
        ).bindparams(staff_profile_id=str(principal.staff_profile_id))
    ).all()
    return [
        TeacherTaskRead(
            id=row[0],
            automation_case_id=row[1],
            student_profile_id=row[2],
            student_name=row[3],
            student_code=row[4],
            section_id=row[5],
            section_name=row[6],
            title=row[7],
            description=row[8],
            status=row[9],
            due_at=row[10],
            escalate_at=row[11],
            acknowledged_at=row[12],
            completed_at=row[13],
            completion_note=row[14],
        )
        for row in rows
    ]


def _teacher_task_scope(
    session: Session,
    principal: TeacherPrincipal,
    task_id: UUID,
):
    row = session.exec(
        text(
            """
            SELECT t.id, t.automation_case_id, t.status, c.section_id
            FROM automation_tasks t
            JOIN automation_cases c ON c.id = t.automation_case_id
            WHERE t.id = CAST(:task_id AS uuid)
              AND t.assigned_role_code = 'TEACHER'
            LIMIT 1
            """
        ).bindparams(task_id=str(task_id))
    ).first()
    if row is None or not _section_in_scope(session, principal, row[3]):
        raise HTTPException(
            status_code=403,
            detail="Task is outside the current teacher scope",
        )
    return row


def acknowledge_teacher_task(
    session: Session,
    principal: TeacherPrincipal,
    task_id: UUID,
):
    _teacher_task_scope(session, principal, task_id)
    task = acknowledge_task(session, principal, task_id)
    _audit(
        session,
        principal,
        "TEACHER_TASK_ACKNOWLEDGED",
        "AutomationTask",
        task.id,
        {"case_id": str(task.automation_case_id)},
    )
    session.commit()
    return task


def complete_teacher_task(
    session: Session,
    principal: TeacherPrincipal,
    task_id: UUID,
    payload: TeacherTaskComplete,
):
    _teacher_task_scope(session, principal, task_id)
    task = complete_task(
        session,
        principal,
        task_id,
        TaskComplete(completion_note=payload.completion_note),
    )
    _audit(
        session,
        principal,
        "TEACHER_TASK_COMPLETED",
        "AutomationTask",
        task.id,
        {
            "case_id": str(task.automation_case_id),
            "completion_note": payload.completion_note,
        },
    )
    session.commit()
    return task
