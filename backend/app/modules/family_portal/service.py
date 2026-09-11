from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.access import GuardianPrincipal
from app.api.deps import CurrentPrincipal
from app.modules.families.models import GuardianProfile
from app.modules.family_portal.models import (
    FamilyNotice,
    FamilyNoticeReceipt,
    GuardianStudentPortalAccess,
)
from app.modules.family_portal.schemas import (
    AttendanceItem,
    BootstrapAccessResult,
    ChildCard,
    ChildOverview,
    FamilyNoticeCreate,
    FamilyNoticeRead,
    GradeItem,
    GuardianMe,
    NoticeAcknowledgeResult,
    PortalGrantCreate,
)
from app.modules.students.models import StudentProfile


def _guardian_has_student(
    session: Session,
    guardian_profile_id: UUID,
    student_profile_id: UUID,
) -> bool:
    grant = session.exec(
        select(GuardianStudentPortalAccess).where(
            GuardianStudentPortalAccess.guardian_profile_id == guardian_profile_id,
            GuardianStudentPortalAccess.student_profile_id == student_profile_id,
            GuardianStudentPortalAccess.status == "ACTIVE",
        )
    ).first()
    return grant is not None


def _require_child_access(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> None:
    if not _guardian_has_student(
        session,
        guardian.guardian_profile_id,
        student_profile_id,
    ):
        raise HTTPException(status_code=404, detail="Student not available in family portal")


def guardian_me(session: Session, guardian: GuardianPrincipal) -> GuardianMe:
    row = session.exec(
        text(
            """
            SELECT p.given_names, p.family_names
            FROM guardian_profiles gp
            JOIN persons p ON p.id = gp.person_id
            WHERE gp.id = :guardian_profile_id
            """
        ).bindparams(guardian_profile_id=str(guardian.guardian_profile_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Guardian profile not found")

    count_row = session.exec(
        text(
            """
            SELECT COUNT(*)
            FROM guardian_student_portal_access
            WHERE guardian_profile_id = :guardian_profile_id
              AND status = 'ACTIVE'
            """
        ).bindparams(guardian_profile_id=str(guardian.guardian_profile_id))
    ).first()

    return GuardianMe(
        guardian_profile_id=guardian.guardian_profile_id,
        given_names=row[0],
        family_names=row[1],
        linked_children=int(count_row[0] or 0),
    )


def children(session: Session, guardian: GuardianPrincipal) -> list[ChildCard]:
    rows = session.exec(
        text(
            """
            SELECT
                sp.id,
                p.given_names,
                p.family_names,
                sgr.relationship_type,
                ap.name,
                gl.name,
                s.name
            FROM guardian_student_portal_access pa
            JOIN student_profiles sp ON sp.id = pa.student_profile_id
            JOIN persons p ON p.id = sp.person_id
            LEFT JOIN student_guardian_relationships sgr
              ON sgr.student_profile_id = sp.id
             AND sgr.guardian_profile_id = pa.guardian_profile_id
            LEFT JOIN enrollments e
              ON e.student_profile_id = sp.id
             AND e.status = 'ACTIVE'
            LEFT JOIN academic_periods ap ON ap.id = e.academic_period_id
            LEFT JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
             AND ssa.status = 'ACTIVE'
            LEFT JOIN sections s ON s.id = ssa.section_id
            LEFT JOIN grade_levels gl ON gl.id = s.grade_level_id
            WHERE pa.guardian_profile_id = :guardian_profile_id
              AND pa.status = 'ACTIVE'
              AND sp.status = 'ACTIVE'
            ORDER BY p.family_names, p.given_names
            """
        ).bindparams(guardian_profile_id=str(guardian.guardian_profile_id))
    ).all()

    return [
        ChildCard(
            student_profile_id=row[0],
            given_names=row[1],
            family_names=row[2],
            relationship_type=row[3],
            academic_period_name=row[4],
            grade_name=row[5],
            section_name=row[6],
        )
        for row in rows
    ]


def child_overview(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> ChildOverview:
    _require_child_access(session, guardian, student_profile_id)

    attendance = session.exec(
        text(
            """
            SELECT
                COUNT(ar.id),
                COALESCE(SUM(CASE WHEN ac.counts_as_present THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN ac.counts_as_absent THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN ac.counts_as_late THEN 1 ELSE 0 END), 0)
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
            LEFT JOIN attendance_records ar
              ON ar.student_section_assignment_id = ssa.id
            LEFT JOIN attendance_codes ac
              ON ac.id = ar.attendance_code_id
            WHERE e.student_profile_id = :student_profile_id
              AND e.status = 'ACTIVE'
              AND ssa.status = 'ACTIVE'
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).first()

    total = int(attendance[0] or 0)
    present = int(attendance[1] or 0)
    absent = int(attendance[2] or 0)
    late = int(attendance[3] or 0)

    grades = session.exec(
        text(
            """
            SELECT
                AVG((ge.score / NULLIF(a.max_score, 0)) * 100.0)
                  FILTER (WHERE ge.status = 'GRADED' AND ge.score IS NOT NULL),
                COUNT(ge.id) FILTER (WHERE ge.status = 'MISSING'),
                COUNT(ge.id) FILTER (WHERE ge.status = 'GRADED')
            FROM enrollments e
            JOIN student_section_assignments ssa
              ON ssa.enrollment_id = e.id
            LEFT JOIN grade_entries ge
              ON ge.student_section_assignment_id = ssa.id
            LEFT JOIN assessments a ON a.id = ge.assessment_id
            WHERE e.student_profile_id = :student_profile_id
              AND e.status = 'ACTIVE'
              AND ssa.status = 'ACTIVE'
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).first()

    avg = float(grades[0]) if grades[0] is not None else None

    return ChildOverview(
        student_profile_id=student_profile_id,
        attendance_rate=round((present / total) * 100.0, 2) if total else None,
        absence_count=absent,
        late_count=late,
        academic_average_percent=round(avg, 2) if avg is not None else None,
        missing_assessments=int(grades[1] or 0),
        graded_entries=int(grades[2] or 0),
    )


def child_attendance(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
    limit: int,
) -> list[AttendanceItem]:
    _require_child_access(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                cs.session_date,
                sub.name,
                ac.code,
                ac.label,
                ac.semantic,
                ar.minutes_late
            FROM enrollments e
            JOIN student_section_assignments ssa ON ssa.enrollment_id = e.id
            JOIN attendance_records ar
              ON ar.student_section_assignment_id = ssa.id
            JOIN class_sessions cs ON cs.id = ar.class_session_id
            JOIN attendance_codes ac ON ac.id = ar.attendance_code_id
            LEFT JOIN course_offerings co ON co.id = cs.course_offering_id
            LEFT JOIN subjects sub ON sub.id = co.subject_id
            WHERE e.student_profile_id = :student_profile_id
            ORDER BY cs.session_date DESC, cs.starts_at DESC
            LIMIT :limit
            """
        ).bindparams(
            student_profile_id=str(student_profile_id),
            limit=limit,
        )
    ).all()

    return [
        AttendanceItem(
            session_date=row[0],
            subject_name=row[1],
            code=row[2],
            label=row[3],
            semantic=row[4],
            minutes_late=int(row[5] or 0),
        )
        for row in rows
    ]


def child_grades(
    session: Session,
    guardian: GuardianPrincipal,
    student_profile_id: UUID,
) -> list[GradeItem]:
    _require_child_access(session, guardian, student_profile_id)

    rows = session.exec(
        text(
            """
            SELECT
                a.id,
                sub.name,
                gp.name,
                a.title,
                a.due_on,
                a.max_score,
                ge.score,
                ge.status,
                ge.feedback
            FROM enrollments e
            JOIN student_section_assignments ssa ON ssa.enrollment_id = e.id
            JOIN grade_entries ge
              ON ge.student_section_assignment_id = ssa.id
            JOIN assessments a ON a.id = ge.assessment_id
            LEFT JOIN course_offerings co ON co.id = a.course_offering_id
            LEFT JOIN subjects sub ON sub.id = co.subject_id
            LEFT JOIN grading_periods gp ON gp.id = a.grading_period_id
            WHERE e.student_profile_id = :student_profile_id
            ORDER BY gp.sequence NULLS LAST, a.due_on DESC NULLS LAST, a.title
            """
        ).bindparams(student_profile_id=str(student_profile_id))
    ).all()

    return [
        GradeItem(
            assessment_id=row[0],
            subject_name=row[1],
            grading_period_name=row[2],
            title=row[3],
            due_on=row[4],
            max_score=float(row[5]),
            score=float(row[6]) if row[6] is not None else None,
            status=row[7],
            feedback=row[8],
        )
        for row in rows
    ]


def list_portal_notices(
    session: Session,
    guardian: GuardianPrincipal,
) -> list[FamilyNoticeRead]:
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
             AND r.guardian_profile_id = :guardian_profile_id
            WHERE n.status = 'PUBLISHED'
              AND (
                n.student_profile_id IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM guardian_student_portal_access pa
                    WHERE pa.guardian_profile_id = :guardian_profile_id
                      AND pa.student_profile_id = n.student_profile_id
                      AND pa.status = 'ACTIVE'
                )
              )
            ORDER BY n.published_at DESC NULLS LAST, n.created_at DESC
            """
        ).bindparams(guardian_profile_id=str(guardian.guardian_profile_id))
    ).all()

    now = datetime.now(UTC)
    result: list[FamilyNoticeRead] = []

    for row in rows:
        if row[7] is None:
            receipt = session.exec(
                select(FamilyNoticeReceipt).where(
                    FamilyNoticeReceipt.family_notice_id == row[0],
                    FamilyNoticeReceipt.guardian_profile_id == guardian.guardian_profile_id,
                )
            ).first()
            if receipt is None:
                receipt = FamilyNoticeReceipt(
                    organization_id=guardian.organization_id,
                    institution_id=guardian.institution_id,
                    family_notice_id=row[0],
                    guardian_profile_id=guardian.guardian_profile_id,
                    read_at=now,
                )
            else:
                receipt.read_at = now
            session.add(receipt)

        result.append(
            FamilyNoticeRead(
                id=row[0],
                student_profile_id=row[1],
                notice_type=row[2],
                title=row[3],
                body=row[4],
                requires_acknowledgement=row[5],
                published_at=row[6],
                read_at=row[7] or now,
                acknowledged_at=row[8],
            )
        )

    session.commit()
    return result


def acknowledge_notice(
    session: Session,
    guardian: GuardianPrincipal,
    notice_id: UUID,
) -> NoticeAcknowledgeResult:
    notice = session.get(FamilyNotice, notice_id)
    if notice is None or notice.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="Published notice not found")

    if notice.student_profile_id is not None and not _guardian_has_student(
        session,
        guardian.guardian_profile_id,
        notice.student_profile_id,
    ):
        raise HTTPException(status_code=404, detail="Notice not available")

    now = datetime.now(UTC)
    receipt = session.exec(
        select(FamilyNoticeReceipt).where(
            FamilyNoticeReceipt.family_notice_id == notice_id,
            FamilyNoticeReceipt.guardian_profile_id == guardian.guardian_profile_id,
        )
    ).first()

    if receipt is None:
        receipt = FamilyNoticeReceipt(
            organization_id=guardian.organization_id,
            institution_id=guardian.institution_id,
            family_notice_id=notice_id,
            guardian_profile_id=guardian.guardian_profile_id,
            read_at=now,
            acknowledged_at=now,
        )
    else:
        receipt.read_at = receipt.read_at or now
        receipt.acknowledged_at = now

    session.add(receipt)
    session.commit()

    return NoticeAcknowledgeResult(
        family_notice_id=notice_id,
        guardian_profile_id=guardian.guardian_profile_id,
        acknowledged_at=now,
    )


# Staff administration


def create_grant(
    session: Session,
    principal: CurrentPrincipal,
    payload: PortalGrantCreate,
) -> GuardianStudentPortalAccess:
    guardian = session.get(GuardianProfile, payload.guardian_profile_id)
    student = session.get(StudentProfile, payload.student_profile_id)
    if guardian is None:
        raise HTTPException(status_code=404, detail="Guardian profile not found")
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")

    existing = session.exec(
        select(GuardianStudentPortalAccess).where(
            GuardianStudentPortalAccess.guardian_profile_id == payload.guardian_profile_id,
            GuardianStudentPortalAccess.student_profile_id == payload.student_profile_id,
        )
    ).first()

    now = datetime.now(UTC)
    if existing:
        existing.status = "ACTIVE"
        existing.access_level = payload.access_level
        existing.granted_at = now
        existing.revoked_at = None
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    entity = GuardianStudentPortalAccess(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def revoke_grant(
    session: Session,
    grant_id: UUID,
) -> GuardianStudentPortalAccess:
    grant = session.get(GuardianStudentPortalAccess, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Portal grant not found")
    grant.status = "REVOKED"
    grant.revoked_at = datetime.now(UTC)
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


def bootstrap_grants(
    session: Session,
    principal: CurrentPrincipal,
) -> BootstrapAccessResult:
    rows = session.exec(
        text(
            """
            SELECT guardian_profile_id, student_profile_id
            FROM student_guardian_relationships
            WHERE is_legal_guardian = true OR is_primary_contact = true
            """
        )
    ).all()

    created = 0
    existing_count = 0
    for guardian_id, student_id in rows:
        existing = session.exec(
            select(GuardianStudentPortalAccess).where(
                GuardianStudentPortalAccess.guardian_profile_id == guardian_id,
                GuardianStudentPortalAccess.student_profile_id == student_id,
            )
        ).first()
        if existing:
            existing_count += 1
            continue

        session.add(
            GuardianStudentPortalAccess(
                organization_id=principal.organization_id,
                institution_id=principal.institution_id,
                guardian_profile_id=guardian_id,
                student_profile_id=student_id,
                access_level="STANDARD",
                status="ACTIVE",
            )
        )
        created += 1

    session.commit()
    return BootstrapAccessResult(created=created, existing=existing_count)


def create_notice(
    session: Session,
    principal: CurrentPrincipal,
    payload: FamilyNoticeCreate,
) -> FamilyNotice:
    if payload.student_profile_id is not None:
        student = session.get(StudentProfile, payload.student_profile_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Student profile not found")

    now = datetime.now(UTC)
    data = payload.model_dump(exclude={"publish_now"})
    entity = FamilyNotice(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        created_by_user_id=principal.user_id,
        status="PUBLISHED" if payload.publish_now else "DRAFT",
        published_at=now if payload.publish_now else None,
        **data,
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def publish_notice(session: Session, notice_id: UUID) -> FamilyNotice:
    notice = session.get(FamilyNotice, notice_id)
    if notice is None:
        raise HTTPException(status_code=404, detail="Family notice not found")
    if notice.status == "ARCHIVED":
        raise HTTPException(status_code=409, detail="Archived notice cannot be published")
    if notice.status != "PUBLISHED":
        notice.status = "PUBLISHED"
        notice.published_at = datetime.now(UTC)
        session.add(notice)
        session.commit()
        session.refresh(notice)
    return notice
