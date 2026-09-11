from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import GuardianPrincipal
from app.modules.family_portal.service import acknowledge_notice
from app.modules.guardian_console.schemas import (
    GuardianAttendanceRead,
    GuardianClassRead,
    GuardianConsoleMe,
    GuardianGradeRead,
    GuardianNoticeAcknowledge,
    GuardianNoticeRead,
    GuardianPendingRead,
    GuardianProgressRead,
    GuardianScheduleRead,
    GuardianStudentCard,
    GuardianStudentSummary,
)


def _require_student_scope(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> str:
    row = session.exec(
        text(
            """
            SELECT pa.access_level
            FROM guardian_student_portal_access pa
            JOIN student_profiles sp ON sp.id = pa.student_profile_id
            WHERE pa.guardian_profile_id =
                  CAST(:guardian_profile_id AS uuid)
              AND pa.student_profile_id =
                  CAST(:student_profile_id AS uuid)
              AND pa.institution_id =
                  CAST(:institution_id AS uuid)
              AND pa.status = 'ACTIVE'
              AND sp.status = 'ACTIVE'
            LIMIT 1
            """
        ).bindparams(
            guardian_profile_id=str(guardian.guardian_profile_id),
            student_profile_id=str(student_profile_id),
            institution_id=str(guardian.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Student not available in Guardian Console",
        )
    return str(row[0])


def guardian_me(
    session: Session,
    guardian: GuardianPrincipal,
) -> GuardianConsoleMe:
    row = session.exec(
        text(
            """
            SELECT
                trim(concat_ws(' ', p.given_names, p.family_names)),
                p.primary_email,
                (
                    SELECT COUNT(*)
                    FROM guardian_student_portal_access pa
                    JOIN student_profiles sp
                      ON sp.id = pa.student_profile_id
                     AND sp.status = 'ACTIVE'
                    WHERE pa.guardian_profile_id = gp.id
                      AND pa.status = 'ACTIVE'
                )
            FROM guardian_profiles gp
            JOIN persons p ON p.id = gp.person_id
            WHERE gp.id = CAST(:guardian_profile_id AS uuid)
              AND gp.institution_id = CAST(:institution_id AS uuid)
              AND gp.status = 'ACTIVE'
            """
        ).bindparams(
            guardian_profile_id=str(guardian.guardian_profile_id),
            institution_id=str(guardian.institution_id),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Active guardian profile not found",
        )

    return GuardianConsoleMe(
        guardian_profile_id=guardian.guardian_profile_id,
        guardian_name=row[0],
        primary_email=row[1],
        linked_students=int(row[2] or 0),
    )


def guardian_students(
    session: Session,
    guardian: GuardianPrincipal,
) -> list[GuardianStudentCard]:
    rows = session.exec(
        text(
            """
            SELECT
                sp.id,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                sp.student_code,
                pa.access_level,
                sgr.relationship_type,
                ctx.academic_period_name,
                ctx.grade_name,
                ctx.section_name
            FROM guardian_student_portal_access pa
            JOIN student_profiles sp
              ON sp.id = pa.student_profile_id
             AND sp.status = 'ACTIVE'
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN student_guardian_relationships sgr
              ON sgr.guardian_profile_id = pa.guardian_profile_id
             AND sgr.student_profile_id = pa.student_profile_id
            LEFT JOIN LATERAL (
                SELECT
                    ap.name AS academic_period_name,
                    gl.name AS grade_name,
                    sec.name AS section_name
                FROM enrollments e
                JOIN academic_periods ap ON ap.id = e.academic_period_id
                LEFT JOIN student_section_assignments ssa
                  ON ssa.enrollment_id = e.id
                 AND ssa.status = 'ACTIVE'
                LEFT JOIN sections sec ON sec.id = ssa.section_id
                LEFT JOIN grade_levels gl ON gl.id = sec.grade_level_id
                WHERE e.student_profile_id = sp.id
                  AND e.status = 'ACTIVE'
                ORDER BY ap.starts_on DESC, e.created_at DESC
                LIMIT 1
            ) AS ctx ON true
            WHERE pa.guardian_profile_id =
                  CAST(:guardian_profile_id AS uuid)
              AND pa.institution_id =
                  CAST(:institution_id AS uuid)
              AND pa.status = 'ACTIVE'
            ORDER BY p.family_names, p.given_names
            """
        ).bindparams(
            guardian_profile_id=str(guardian.guardian_profile_id),
            institution_id=str(guardian.institution_id),
        )
    ).all()

    return [
        GuardianStudentCard(
            student_profile_id=row[0],
            student_name=row[1],
            student_code=row[2],
            access_level=row[3],
            relationship_type=row[4],
            academic_period_name=row[5],
            grade_name=row[6],
            section_name=row[7],
        )
        for row in rows
    ]


def guardian_student_summary(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> GuardianStudentSummary:
    _require_student_scope(session, guardian, student_profile_id)

    row = session.exec(
        text(
            """
            WITH current_ssa AS (
                SELECT ssa.id, ssa.section_id, ssa.academic_period_id
                FROM enrollments e
                JOIN student_section_assignments ssa
                  ON ssa.enrollment_id = e.id
                 AND ssa.status = 'ACTIVE'
                WHERE e.student_profile_id =
                      CAST(:student_profile_id AS uuid)
                  AND e.status = 'ACTIVE'
            ),
            current_courses AS (
                SELECT DISTINCT co.id
                FROM current_ssa cssa
                JOIN course_offerings co
                  ON co.section_id = cssa.section_id
                 AND co.academic_period_id = cssa.academic_period_id
                 AND co.status = 'ACTIVE'
            ),
            attendance AS (
                SELECT
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_present
                    ) AS present_count,
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_absent
                    ) AS absent_count,
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_late
                    ) AS late_count,
                    COUNT(*) AS total_count
                FROM attendance_records ar
                JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
                WHERE ar.student_section_assignment_id IN (
                    SELECT id FROM current_ssa
                )
            ),
            grades AS (
                SELECT
                    AVG(
                        CASE
                            WHEN ge.status = 'GRADED'
                             AND ge.score IS NOT NULL
                             AND a.max_score > 0
                            THEN (ge.score / a.max_score) * 100.0
                            ELSE NULL
                        END
                    ) AS average_percent
                FROM grade_entries ge
                JOIN assessments a ON a.id = ge.assessment_id
                WHERE ge.student_section_assignment_id IN (
                    SELECT id FROM current_ssa
                )
                  AND a.course_offering_id IN (
                    SELECT id FROM current_courses
                )
            ),
            pending AS (
                SELECT COUNT(*) AS pending_count
                FROM current_courses cc
                JOIN assessments a ON a.course_offering_id = cc.id
                JOIN current_ssa cssa
                  ON cssa.section_id = a.section_id
                LEFT JOIN grade_entries ge
                  ON ge.assessment_id = a.id
                 AND ge.student_section_assignment_id = cssa.id
                WHERE ge.id IS NULL
                   OR ge.status IN ('PENDING', 'MISSING')
            )
            SELECT
                COALESCE((SELECT present_count FROM attendance), 0),
                COALESCE((SELECT absent_count FROM attendance), 0),
                COALESCE((SELECT late_count FROM attendance), 0),
                COALESCE((SELECT total_count FROM attendance), 0),
                (SELECT average_percent FROM grades),
                COALESCE((SELECT pending_count FROM pending), 0),
                (
                    SELECT COUNT(*)
                    FROM family_notices fn
                    WHERE fn.status = 'PUBLISHED'
                      AND (
                          fn.student_profile_id IS NULL
                          OR fn.student_profile_id =
                             CAST(:student_profile_id AS uuid)
                      )
                )
            """
        ).bindparams(
            student_profile_id=str(student_profile_id),
        )
    ).first()

    assert row is not None
    present = int(row[0] or 0)
    total = int(row[3] or 0)
    return GuardianStudentSummary(
        student_profile_id=student_profile_id,
        attendance_present=present,
        attendance_absent=int(row[1] or 0),
        attendance_late=int(row[2] or 0),
        attendance_rate=(
            round((present / total) * 100.0, 2) if total else None
        ),
        academic_average_percent=(
            round(float(row[4]), 2) if row[4] is not None else None
        ),
        pending_assessments=int(row[5] or 0),
        visible_notices=int(row[6] or 0),
    )


def guardian_student_classes(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianClassRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                co.id,
                sub.code,
                sub.name,
                sub.area,
                sec.name,
                COALESCE(
                    array_agg(
                        DISTINCT trim(
                            concat_ws(' ', tp.given_names, tp.family_names)
                        )
                    ) FILTER (WHERE tp.id IS NOT NULL),
                    ARRAY[]::text[]
                ) AS teachers
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            JOIN sections sec ON sec.id = ssa.section_id
            JOIN course_offerings co
              ON co.section_id = ssa.section_id
             AND co.academic_period_id = ssa.academic_period_id
             AND co.status = 'ACTIVE'
            JOIN subjects sub ON sub.id = co.subject_id
            LEFT JOIN teaching_assignments ta
              ON ta.course_offering_id = co.id
             AND (
                 ta.starts_on IS NULL
                 OR ta.starts_on <= CURRENT_DATE
             )
             AND (
                 ta.ends_on IS NULL
                 OR ta.ends_on >= CURRENT_DATE
             )
            LEFT JOIN staff_profiles tsp ON tsp.id = ta.staff_profile_id
            LEFT JOIN persons tp ON tp.id = tsp.person_id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
              AND e.status = 'ACTIVE'
            GROUP BY
                co.id,
                sub.code,
                sub.name,
                sub.area,
                sec.name
            ORDER BY sub.name
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GuardianClassRead(
            course_offering_id=row[0],
            subject_code=row[1],
            subject_name=row[2],
            subject_area=row[3],
            section_name=row[4],
            teachers=list(row[5] or []),
        )
        for row in rows
    ]


def guardian_student_schedule(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianScheduleRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                ss.id,
                co.id,
                ss.weekday,
                ss.starts_at,
                ss.ends_at,
                ss.room_label,
                sub.name,
                sub.code
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            JOIN course_offerings co
              ON co.section_id = ssa.section_id
             AND co.academic_period_id = ssa.academic_period_id
             AND co.status = 'ACTIVE'
            JOIN subjects sub ON sub.id = co.subject_id
            JOIN schedule_slots ss ON ss.course_offering_id = co.id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
              AND e.status = 'ACTIVE'
            ORDER BY ss.weekday, ss.starts_at, sub.name
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GuardianScheduleRead(
            schedule_slot_id=row[0],
            course_offering_id=row[1],
            weekday=int(row[2]),
            starts_at=row[3],
            ends_at=row[4],
            room_label=row[5],
            subject_name=row[6],
            subject_code=row[7],
        )
        for row in rows
    ]


def guardian_student_attendance(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianAttendanceRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                ar.id,
                cs.session_date,
                sub.name,
                sub.code,
                ac.code,
                ac.label,
                ac.semantic,
                ar.minutes_late,
                ar.note
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
            JOIN attendance_records ar
              ON ar.student_section_assignment_id = ssa.id
            JOIN class_sessions cs ON cs.id = ar.class_session_id
            JOIN course_offerings co ON co.id = cs.course_offering_id
            JOIN subjects sub ON sub.id = co.subject_id
            JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
            ORDER BY cs.session_date DESC, cs.starts_at DESC
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GuardianAttendanceRead(
            attendance_record_id=row[0],
            session_date=row[1],
            subject_name=row[2],
            subject_code=row[3],
            attendance_code=row[4],
            attendance_label=row[5],
            semantic=row[6],
            minutes_late=int(row[7] or 0),
            note=row[8],
        )
        for row in rows
    ]


def guardian_student_grades(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianGradeRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                a.id,
                ge.id,
                sub.name,
                sub.code,
                gp.name,
                cat.name,
                a.title,
                a.due_on,
                a.max_score,
                ge.score,
                ge.status,
                ge.feedback,
                CASE
                    WHEN ge.score IS NOT NULL AND a.max_score > 0
                    THEN (ge.score / a.max_score) * 100.0
                    ELSE NULL
                END AS percentage
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
            JOIN grade_entries ge
              ON ge.student_section_assignment_id = ssa.id
            JOIN assessments a ON a.id = ge.assessment_id
            JOIN assessment_categories cat
              ON cat.id = a.assessment_category_id
            JOIN grading_periods gp ON gp.id = a.grading_period_id
            JOIN course_offerings co ON co.id = a.course_offering_id
            JOIN subjects sub ON sub.id = co.subject_id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
            ORDER BY
                gp.sequence DESC,
                COALESCE(a.due_on, CURRENT_DATE) DESC,
                sub.name,
                a.title
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GuardianGradeRead(
            assessment_id=row[0],
            grade_entry_id=row[1],
            subject_name=row[2],
            subject_code=row[3],
            grading_period_name=row[4],
            category_name=row[5],
            assessment_title=row[6],
            due_on=row[7],
            max_score=float(row[8]),
            score=float(row[9]) if row[9] is not None else None,
            status=row[10],
            feedback=row[11],
            percentage=(
                round(float(row[12]), 2)
                if row[12] is not None
                else None
            ),
        )
        for row in rows
    ]


def guardian_student_pending(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianPendingRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                a.id,
                sub.name,
                sub.code,
                a.title,
                a.due_on,
                COALESCE(ge.status, 'PENDING') AS grade_status
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            JOIN course_offerings co
              ON co.section_id = ssa.section_id
             AND co.academic_period_id = ssa.academic_period_id
             AND co.status = 'ACTIVE'
            JOIN subjects sub ON sub.id = co.subject_id
            JOIN assessments a ON a.course_offering_id = co.id
            LEFT JOIN grade_entries ge
              ON ge.assessment_id = a.id
             AND ge.student_section_assignment_id = ssa.id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
              AND e.status = 'ACTIVE'
              AND (
                  ge.id IS NULL
                  OR ge.status IN ('PENDING', 'MISSING')
              )
            ORDER BY a.due_on NULLS LAST, sub.name, a.title
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    today = date.today()
    return [
        GuardianPendingRead(
            assessment_id=row[0],
            subject_name=row[1],
            subject_code=row[2],
            assessment_title=row[3],
            due_on=row[4],
            status=row[5],
            overdue=bool(row[4] is not None and row[4] < today),
        )
        for row in rows
    ]


def guardian_student_progress(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GuardianProgressRead]:
    _require_student_scope(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            WITH current_ssa AS (
                SELECT
                    ssa.id,
                    ssa.section_id,
                    ssa.academic_period_id
                FROM enrollments e
                JOIN student_section_assignments ssa
                  ON ssa.enrollment_id = e.id
                 AND ssa.status = 'ACTIVE'
                WHERE e.student_profile_id =
                      CAST(:student_profile_id AS uuid)
                  AND e.status = 'ACTIVE'
            ),
            courses AS (
                SELECT DISTINCT
                    co.id,
                    sub.name AS subject_name,
                    sub.code AS subject_code
                FROM current_ssa cssa
                JOIN course_offerings co
                  ON co.section_id = cssa.section_id
                 AND co.academic_period_id = cssa.academic_period_id
                 AND co.status = 'ACTIVE'
                JOIN subjects sub ON sub.id = co.subject_id
            ),
            grade_agg AS (
                SELECT
                    a.course_offering_id,
                    AVG(
                        CASE
                            WHEN ge.status = 'GRADED'
                             AND ge.score IS NOT NULL
                             AND a.max_score > 0
                            THEN (ge.score / a.max_score) * 100.0
                            ELSE NULL
                        END
                    ) AS average_percent,
                    COUNT(*) FILTER (
                        WHERE ge.status = 'GRADED'
                          AND ge.score IS NOT NULL
                    ) AS graded_items,
                    COUNT(*) FILTER (
                        WHERE ge.status = 'MISSING'
                    ) AS missing_items
                FROM current_ssa cssa
                JOIN grade_entries ge
                  ON ge.student_section_assignment_id = cssa.id
                JOIN assessments a ON a.id = ge.assessment_id
                GROUP BY a.course_offering_id
            ),
            attendance_agg AS (
                SELECT
                    cs.course_offering_id,
                    COUNT(*) AS attendance_records,
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_present
                    ) AS present_records,
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_absent
                    ) AS absent_records,
                    COUNT(*) FILTER (
                        WHERE ac.counts_as_late
                    ) AS late_records
                FROM current_ssa cssa
                JOIN attendance_records ar
                  ON ar.student_section_assignment_id = cssa.id
                JOIN class_sessions cs ON cs.id = ar.class_session_id
                JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
                GROUP BY cs.course_offering_id
            )
            SELECT
                c.id,
                c.subject_name,
                c.subject_code,
                ga.average_percent,
                COALESCE(ga.graded_items, 0),
                COALESCE(ga.missing_items, 0),
                COALESCE(aa.attendance_records, 0),
                COALESCE(aa.present_records, 0),
                COALESCE(aa.absent_records, 0),
                COALESCE(aa.late_records, 0)
            FROM courses c
            LEFT JOIN grade_agg ga
              ON ga.course_offering_id = c.id
            LEFT JOIN attendance_agg aa
              ON aa.course_offering_id = c.id
            ORDER BY c.subject_name
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GuardianProgressRead(
            course_offering_id=row[0],
            subject_name=row[1],
            subject_code=row[2],
            academic_average_percent=(
                round(float(row[3]), 2)
                if row[3] is not None
                else None
            ),
            graded_items=int(row[4] or 0),
            missing_items=int(row[5] or 0),
            attendance_records=int(row[6] or 0),
            present_records=int(row[7] or 0),
            absent_records=int(row[8] or 0),
            late_records=int(row[9] or 0),
        )
        for row in rows
    ]


def guardian_notices(
    session: Session,
    guardian: GuardianPrincipal,
) -> list[GuardianNoticeRead]:
    rows = session.exec(
        text(
            """
            SELECT
                n.id,
                n.student_profile_id,
                n.notice_type,
                n.title,
                n.body,
                n.requires_acknowledgement,
                n.published_at,
                r.read_at,
                r.acknowledged_at
            FROM family_notices n
            LEFT JOIN family_notice_receipts r
              ON r.family_notice_id = n.id
             AND r.guardian_profile_id =
                 CAST(:guardian_profile_id AS uuid)
            WHERE n.status = 'PUBLISHED'
              AND (
                  n.student_profile_id IS NULL
                  OR EXISTS (
                      SELECT 1
                      FROM guardian_student_portal_access pa
                      WHERE pa.guardian_profile_id =
                            CAST(:guardian_profile_id AS uuid)
                        AND pa.student_profile_id =
                            n.student_profile_id
                        AND pa.institution_id =
                            CAST(:institution_id AS uuid)
                        AND pa.status = 'ACTIVE'
                  )
              )
            ORDER BY n.published_at DESC NULLS LAST, n.created_at DESC
            """
        ).bindparams(
            guardian_profile_id=str(guardian.guardian_profile_id),
            institution_id=str(guardian.institution_id),
        )
    ).all()

    return [
        GuardianNoticeRead(
            notice_id=row[0],
            student_profile_id=row[1],
            notice_type=row[2],
            title=row[3],
            body=row[4],
            requires_acknowledgement=bool(row[5]),
            published_at=row[6],
            read_at=row[7],
            acknowledged_at=row[8],
            scope="GENERAL" if row[1] is None else "STUDENT",
        )
        for row in rows
    ]


def acknowledge_guardian_notice(
    session: Session,
    guardian: GuardianPrincipal,
    notice_id: UUID,
) -> GuardianNoticeAcknowledge:
    result = acknowledge_notice(
        session,
        guardian,
        notice_id,
    )
    return GuardianNoticeAcknowledge(
        notice_id=result.family_notice_id,
        guardian_profile_id=result.guardian_profile_id,
        acknowledged_at=result.acknowledged_at,
    )
