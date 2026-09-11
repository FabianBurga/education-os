from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import StudentPrincipal
from app.modules.student_console.schemas import (
    StudentAttendanceRead,
    StudentClassRead,
    StudentGradeRead,
    StudentNoticeRead,
    StudentPendingRead,
    StudentProfileRead,
    StudentProgressRead,
    StudentScheduleRead,
    StudentSummary,
)


def student_profile(
    session: Session,
    principal: StudentPrincipal,
) -> StudentProfileRead:
    row = session.exec(
        text(
            """
            SELECT
                sp.id,
                sp.student_code,
                trim(concat_ws(' ', p.given_names, p.family_names)),
                p.primary_email,
                ctx.enrollment_number,
                ctx.academic_period_id,
                ctx.academic_period_name,
                ctx.campus_name,
                ctx.grade_name,
                ctx.section_name
            FROM student_profiles sp
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN LATERAL (
                SELECT
                    e.enrollment_number,
                    ap.id AS academic_period_id,
                    ap.name AS academic_period_name,
                    c.name AS campus_name,
                    gl.name AS grade_name,
                    sec.name AS section_name
                FROM enrollments e
                JOIN academic_periods ap ON ap.id = e.academic_period_id
                JOIN campuses c ON c.id = e.campus_id
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
            WHERE sp.id = CAST(:student_profile_id AS uuid)
              AND sp.status = 'ACTIVE'
            """
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Active student profile not found",
        )

    return StudentProfileRead(
        student_profile_id=row[0],
        student_code=row[1],
        student_name=row[2],
        primary_email=row[3],
        enrollment_number=row[4],
        academic_period_id=row[5],
        academic_period_name=row[6],
        campus_name=row[7],
        grade_name=row[8],
        section_name=row[9],
    )


def student_summary(
    session: Session,
    principal: StudentPrincipal,
) -> StudentSummary:
    row = session.exec(
        text(
            """
            WITH current_ssa AS (
                SELECT ssa.id, ssa.section_id, ssa.academic_period_id
                FROM enrollments e
                JOIN student_section_assignments ssa
                  ON ssa.enrollment_id = e.id
                 AND ssa.status = 'ACTIVE'
                WHERE e.student_profile_id = CAST(:student_profile_id AS uuid)
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
                    ) AS late_count
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
                (SELECT COUNT(*) FROM current_courses),
                (
                    SELECT COUNT(*)
                    FROM schedule_slots ss
                    WHERE ss.course_offering_id IN (
                        SELECT id FROM current_courses
                    )
                ),
                COALESCE((SELECT present_count FROM attendance), 0),
                COALESCE((SELECT absent_count FROM attendance), 0),
                COALESCE((SELECT late_count FROM attendance), 0),
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
            student_profile_id=str(principal.student_profile_id),
        )
    ).first()

    assert row is not None
    return StudentSummary(
        active_classes=int(row[0] or 0),
        schedule_slots=int(row[1] or 0),
        attendance_present=int(row[2] or 0),
        attendance_absent=int(row[3] or 0),
        attendance_late=int(row[4] or 0),
        academic_average_percent=(
            round(float(row[5]), 2) if row[5] is not None else None
        ),
        pending_assessments=int(row[6] or 0),
        published_notices=int(row[7] or 0),
    )


def student_classes(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentClassRead]:
    rows = session.exec(
        text(
            """
            SELECT
                co.id,
                sub.code,
                sub.name,
                sub.area,
                gl.name,
                sec.name,
                ap.name,
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
            JOIN grade_levels gl ON gl.id = sec.grade_level_id
            JOIN academic_periods ap ON ap.id = ssa.academic_period_id
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
                gl.name,
                sec.name,
                ap.name
            ORDER BY sub.name
            """
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentClassRead(
            course_offering_id=row[0],
            subject_code=row[1],
            subject_name=row[2],
            subject_area=row[3],
            grade_name=row[4],
            section_name=row[5],
            academic_period_name=row[6],
            teachers=list(row[7] or []),
        )
        for row in rows
    ]


def student_schedule(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentScheduleRead]:
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
                sub.code,
                sec.name
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
            JOIN schedule_slots ss ON ss.course_offering_id = co.id
            WHERE e.student_profile_id =
                  CAST(:student_profile_id AS uuid)
              AND e.status = 'ACTIVE'
            ORDER BY ss.weekday, ss.starts_at, sub.name
            """
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentScheduleRead(
            schedule_slot_id=row[0],
            course_offering_id=row[1],
            weekday=int(row[2]),
            starts_at=row[3],
            ends_at=row[4],
            room_label=row[5],
            subject_name=row[6],
            subject_code=row[7],
            section_name=row[8],
        )
        for row in rows
    ]


def student_attendance(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentAttendanceRead]:
    rows = session.exec(
        text(
            """
            SELECT
                ar.id,
                cs.id,
                co.id,
                cs.session_date,
                cs.starts_at,
                cs.ends_at,
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
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentAttendanceRead(
            attendance_record_id=row[0],
            class_session_id=row[1],
            course_offering_id=row[2],
            session_date=row[3],
            starts_at=row[4],
            ends_at=row[5],
            subject_name=row[6],
            subject_code=row[7],
            attendance_code=row[8],
            attendance_label=row[9],
            semantic=row[10],
            minutes_late=int(row[11] or 0),
            note=row[12],
        )
        for row in rows
    ]


def student_grades(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentGradeRead]:
    rows = session.exec(
        text(
            """
            SELECT
                a.id,
                ge.id,
                co.id,
                sub.name,
                sub.code,
                gp.name,
                cat.name,
                a.code,
                a.title,
                a.max_score,
                a.due_on,
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
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentGradeRead(
            assessment_id=row[0],
            grade_entry_id=row[1],
            course_offering_id=row[2],
            subject_name=row[3],
            subject_code=row[4],
            grading_period_name=row[5],
            category_name=row[6],
            assessment_code=row[7],
            assessment_title=row[8],
            max_score=float(row[9]),
            due_on=row[10],
            score=float(row[11]) if row[11] is not None else None,
            status=row[12],
            feedback=row[13],
            percentage=(
                round(float(row[14]), 2)
                if row[14] is not None
                else None
            ),
        )
        for row in rows
    ]


def student_pending(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentPendingRead]:
    rows = session.exec(
        text(
            """
            SELECT
                a.id,
                co.id,
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
            ORDER BY
                a.due_on NULLS LAST,
                sub.name,
                a.title
            """
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    today = date.today()
    return [
        StudentPendingRead(
            assessment_id=row[0],
            course_offering_id=row[1],
            subject_name=row[2],
            subject_code=row[3],
            assessment_title=row[4],
            due_on=row[5],
            status=row[6],
            overdue=bool(row[5] is not None and row[5] < today),
        )
        for row in rows
    ]


def student_progress(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentProgressRead]:
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
                    co.section_id,
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
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentProgressRead(
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


def student_notices(
    session: Session,
    principal: StudentPrincipal,
) -> list[StudentNoticeRead]:
    rows = session.exec(
        text(
            """
            SELECT
                fn.id,
                fn.notice_type,
                fn.title,
                fn.body,
                fn.requires_acknowledgement,
                fn.published_at,
                fn.student_profile_id
            FROM family_notices fn
            WHERE fn.status = 'PUBLISHED'
              AND (
                  fn.student_profile_id IS NULL
                  OR fn.student_profile_id =
                     CAST(:student_profile_id AS uuid)
              )
            ORDER BY fn.published_at DESC NULLS LAST, fn.created_at DESC
            """
        ).bindparams(
            student_profile_id=str(principal.student_profile_id),
        )
    ).all()

    return [
        StudentNoticeRead(
            notice_id=row[0],
            notice_type=row[1],
            title=row[2],
            body=row[3],
            requires_acknowledgement=bool(row[4]),
            published_at=row[5],
            is_personal=bool(row[6] is not None),
        )
        for row in rows
    ]
