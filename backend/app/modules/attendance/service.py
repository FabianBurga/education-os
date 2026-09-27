from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.academics.models import (
    CourseOffering,
    ScheduleSlot,
)
from app.modules.attendance.models import AttendanceCode, AttendanceRecord, ClassSession
from app.modules.attendance.schemas import (
    AttendanceCodeCreate,
    AttendanceExpectedState,
    AttendanceRecordUpsert,
    ClassSessionCreate,
    ClassSessionStatusChange,
)
from app.modules.audit.service import record_audit
from app.modules.enrollment.models import AcademicPeriod
from app.modules.events.service import enqueue_canonical_event


@dataclass(frozen=True)
class AttendanceMutation:
    record: AttendanceRecord
    changed: bool
    event_type: str | None


def require_attendance_permission(
    session: Session, principal: CurrentPrincipal, permission_key: str
) -> None:
    if permission_key not in {
        "attendance.read",
        "attendance.manage",
        "attendance.correct",
    }:
        raise ValueError("Unsupported attendance permission")
    allowed = session.exec(
        text(
            """SELECT 1
            FROM memberships m
            JOIN institutions i ON i.id=m.institution_id
              AND i.organization_id=:organization_id
            JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN roles r ON r.id=mr.role_id AND r.institution_id=m.institution_id
            JOIN role_permissions rp ON rp.role_id=r.id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id=:user_id AND m.institution_id=:institution_id
              AND m.status='ACTIVE'
              AND p.key=:permission LIMIT 1"""
        ),
        params={
            "user_id": principal.user_id,
            "organization_id": principal.organization_id,
            "institution_id": principal.institution_id,
            "permission": permission_key,
        },
    ).first()
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Attendance permission required",
        )


def _get(
    session: Session,
    model,
    entity_id: UUID,
    label: str,
    principal: CurrentPrincipal,
):
    entity = session.exec(
        select(model).where(
            model.id == entity_id,
            model.organization_id == principal.organization_id,
            model.institution_id == principal.institution_id,
        )
    ).first()
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found in current tenant")
    return entity


def list_codes(session: Session, principal: CurrentPrincipal):
    return session.exec(
        select(AttendanceCode)
        .where(
            AttendanceCode.organization_id == principal.organization_id,
            AttendanceCode.institution_id == principal.institution_id,
            AttendanceCode.status == "ACTIVE",
        )
        .order_by(AttendanceCode.code)
    ).all()


def create_code(
    session: Session,
    principal: CurrentPrincipal,
    payload: AttendanceCodeCreate,
):
    entity = AttendanceCode(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_sessions(session: Session, principal: CurrentPrincipal):
    return session.exec(
        select(ClassSession).where(
            ClassSession.organization_id == principal.organization_id,
            ClassSession.institution_id == principal.institution_id,
        ).order_by(
            ClassSession.session_date.desc(),
            ClassSession.starts_at.desc(),
        )
    ).all()


def create_session(
    session: Session,
    principal: CurrentPrincipal,
    payload: ClassSessionCreate,
):
    offering = session.exec(
        select(CourseOffering).where(
            CourseOffering.id == payload.course_offering_id,
            CourseOffering.organization_id == principal.organization_id,
            CourseOffering.institution_id == principal.institution_id,
            CourseOffering.status == "ACTIVE",
        )
    ).first()
    if offering is None:
        raise HTTPException(status_code=404, detail="Course offering not found")
    period = session.exec(
        select(AcademicPeriod).where(
            AcademicPeriod.id == offering.academic_period_id,
            AcademicPeriod.organization_id == principal.organization_id,
            AcademicPeriod.institution_id == principal.institution_id,
            AcademicPeriod.status == "ACTIVE",
        )
    ).first()
    if period is None or not period.starts_on <= payload.session_date <= period.ends_on:
        raise HTTPException(status_code=409, detail="Session date is outside an active academic period")
    if payload.schedule_slot_id:
        slot = session.exec(
            select(ScheduleSlot).where(
                ScheduleSlot.id == payload.schedule_slot_id,
                ScheduleSlot.organization_id == principal.organization_id,
                ScheduleSlot.institution_id == principal.institution_id,
            )
        ).first()
        if slot is None:
            raise HTTPException(status_code=404, detail="Schedule slot not found")
        if slot.course_offering_id != offering.id:
            raise HTTPException(
                status_code=409,
                detail="Schedule slot belongs to another course offering",
            )

    entity = ClassSession(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=offering.section_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def change_class_session_status(
    session: Session,
    principal: CurrentPrincipal,
    class_session_id: UUID,
    payload: ClassSessionStatusChange,
):
    row = session.exec(
        text(
            """SELECT cs.status, cs.course_offering_id, cs.session_date,
                      cs.organization_id, cs.institution_id
               FROM class_sessions cs
               WHERE cs.id=CAST(:session_id AS uuid)
                 AND cs.organization_id=CAST(:organization_id AS uuid)
                 AND cs.institution_id=CAST(:institution_id AS uuid)
               FOR UPDATE"""
        ),
        params={
            "session_id": str(class_session_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Class session not found")
    if row[0] == payload.status:
        return _get(session, ClassSession, class_session_id, "Class session", principal)
    if row[0] != payload.expected_status:
        raise HTTPException(status_code=409, detail="Class session changed; refresh and retry")
    if payload.status == "CANCELLED":
        has_records = session.exec(
            text(
                "SELECT 1 FROM attendance_records WHERE class_session_id="
                "CAST(:session_id AS uuid) LIMIT 1"
            ),
            params={"session_id": str(class_session_id)},
        ).first()
        if has_records is not None:
            raise HTTPException(
                status_code=409,
                detail="A session with attendance records cannot be cancelled",
            )
    session.exec(
        text(
            "UPDATE class_sessions SET status=:new_status "
            "WHERE id=CAST(:session_id AS uuid)"
        ),
        params={"new_status": payload.status, "session_id": str(class_session_id)},
    )
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="CLASS_SESSION_STATUS_CHANGED",
        entity_type="ClassSession",
        entity_id=class_session_id,
        metadata={"previous_status": row[0], "status": payload.status},
    )
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="class.session.status_changed",
        event_version=1,
        aggregate_type="class_session",
        aggregate_id=class_session_id,
        actor_user_id=principal.user_id,
        payload={
            "course_offering_id": str(row[1]),
            "session_date": row[2].isoformat(),
            "previous_status": row[0],
            "status": payload.status,
        },
    )
    session.commit()
    return _get(session, ClassSession, class_session_id, "Class session", principal)


def list_records(session: Session, principal: CurrentPrincipal, class_session_id: UUID):
    _get(session, ClassSession, class_session_id, "Class session", principal)
    return session.exec(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.class_session_id == class_session_id,
            AttendanceRecord.organization_id == principal.organization_id,
            AttendanceRecord.institution_id == principal.institution_id,
        )
        .order_by(AttendanceRecord.created_at)
    ).all()


def _expected_state_matches(
    expected: AttendanceExpectedState | dict | None,
    record: AttendanceRecord,
) -> bool:
    if expected is None:
        return False
    values = expected.model_dump() if hasattr(expected, "model_dump") else expected
    return (
        values["attendance_record_id"] == record.id
        and values["attendance_code_id"] == record.attendance_code_id
        and int(values["minutes_late"] or 0) == int(record.minutes_late or 0)
        and values["note"] == record.note
    )


def _expected_empty_state(expected: AttendanceExpectedState | dict | None) -> bool:
    if expected is None:
        return True
    values = expected.model_dump() if hasattr(expected, "model_dump") else expected
    return (
        values["attendance_record_id"] is None
        and values["attendance_code_id"] is None
        and int(values["minutes_late"] or 0) == 0
        and values["note"] is None
    )


def apply_attendance_record(
    session: Session,
    principal: CurrentPrincipal,
    class_session_id: UUID,
    payload: AttendanceRecordUpsert,
    *,
    expected_state: AttendanceExpectedState | dict | None = None,
    correction_reason: str | None = None,
    source: str = "teacher_online",
    correlation_id: UUID | None = None,
    teacher_scope_required: bool = False,
    allow_historical_correction: bool = False,
    commit: bool = False,
) -> AttendanceMutation:
    """Apply one M3 attendance fact, audit and canonical outbox event atomically."""
    target_lock = (
        "teacher-offline:target:"
        f"{principal.institution_id}:{class_session_id}:"
        f"{payload.student_section_assignment_id}"
    )
    session.exec(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        params={"key": target_lock},
    ).one()
    context = session.exec(
        text(
            """SELECT cs.session_date, cs.status, cs.section_id,
                      co.academic_period_id, ap.starts_on, ap.ends_on, ap.status,
                      sec.campus_id
               FROM class_sessions cs
               JOIN course_offerings co ON co.id=cs.course_offering_id
                 AND co.organization_id=cs.organization_id
                 AND co.institution_id=cs.institution_id
               JOIN academic_periods ap ON ap.id=co.academic_period_id
                 AND ap.organization_id=cs.organization_id
                 AND ap.institution_id=cs.institution_id
               JOIN sections sec ON sec.id=cs.section_id
                 AND sec.organization_id=cs.organization_id
                 AND sec.institution_id=cs.institution_id
               WHERE cs.id=CAST(:session_id AS uuid)
                 AND cs.organization_id=CAST(:organization_id AS uuid)
                 AND cs.institution_id=CAST(:institution_id AS uuid)
                 AND co.status='ACTIVE' AND sec.status='ACTIVE'
               LIMIT 1 FOR UPDATE OF cs"""
        ),
        params={
            "session_id": str(class_session_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if context is None:
        raise HTTPException(status_code=404, detail="Class session not found")
    session_date, session_status, section_id, period_id, period_start, period_end, period_status, campus_id = context
    if session_status != "OPEN":
        raise HTTPException(status_code=409, detail="Class session is not open")
    if period_status != "ACTIVE" or not period_start <= session_date <= period_end:
        raise HTTPException(status_code=409, detail="Class session is outside an active academic period")

    assignment = session.exec(
        text(
            """SELECT ssa.status, ssa.assigned_on, ssa.ended_on, e.status,
                      e.student_profile_id, e.campus_id, sp.status
               FROM student_section_assignments ssa
               JOIN enrollments e ON e.id=ssa.enrollment_id
                 AND e.organization_id=ssa.organization_id
                 AND e.institution_id=ssa.institution_id
               JOIN student_profiles sp ON sp.id=e.student_profile_id
                 AND sp.organization_id=e.organization_id
                 AND sp.institution_id=e.institution_id
               WHERE ssa.id=CAST(:assignment_id AS uuid)
                 AND ssa.organization_id=CAST(:organization_id AS uuid)
                 AND ssa.institution_id=CAST(:institution_id AS uuid)
                 AND ssa.section_id=CAST(:section_id AS uuid)
                 AND ssa.academic_period_id=CAST(:period_id AS uuid)
               LIMIT 1"""
        ),
        params={
            "assignment_id": str(payload.student_section_assignment_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
            "section_id": str(section_id),
            "period_id": str(period_id),
        },
    ).first()
    if (
        assignment is None
        or assignment[5] != campus_id
        or assignment[1] > session_date
        or (assignment[2] is not None and assignment[2] < session_date)
        or assignment[0] not in {"ACTIVE", "TRANSFERRED", "WITHDRAWN"}
    ):
        raise HTTPException(status_code=403, detail="Student is outside the session roster")
    if assignment[3] != "ACTIVE" or assignment[6] != "ACTIVE":
        if not allow_historical_correction:
            raise HTTPException(status_code=403, detail="Student is outside the current attendance scope")
    if teacher_scope_required:
        assigned = session.exec(
            text(
                """SELECT 1 FROM teaching_assignments ta
                   JOIN course_offerings co ON co.id=ta.course_offering_id
                   WHERE ta.staff_profile_id=CAST(:staff_id AS uuid)
                     AND ta.organization_id=CAST(:organization_id AS uuid)
                     AND ta.institution_id=CAST(:institution_id AS uuid)
                     AND ta.course_offering_id=(SELECT course_offering_id FROM class_sessions WHERE id=CAST(:session_id AS uuid))
                     AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE)
                     AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
                     AND (ta.starts_on IS NULL OR ta.starts_on<=:session_date)
                     AND (ta.ends_on IS NULL OR ta.ends_on>=:session_date)
                   LIMIT 1"""
            ),
            params={
                "staff_id": str(getattr(principal, "staff_profile_id", "")),
                "organization_id": str(principal.organization_id),
                "institution_id": str(principal.institution_id),
                "session_id": str(class_session_id),
                "session_date": session_date,
            },
        ).first()
        if assigned is None:
            raise HTTPException(status_code=403, detail="Class session is outside current teacher scope")
    code = session.exec(
        text("""SELECT 1 FROM attendance_codes
               WHERE id=CAST(:code_id AS uuid)
                 AND organization_id=CAST(:organization_id AS uuid)
                 AND institution_id=CAST(:institution_id AS uuid)
                 AND status='ACTIVE'"""),
        params={
            "code_id": str(payload.attendance_code_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if code is None:
        raise HTTPException(status_code=409, detail="Attendance code is not active in this institution")

    existing = session.exec(
        text(
            """SELECT id, attendance_code_id, minutes_late, note
               FROM attendance_records
               WHERE class_session_id=CAST(:session_id AS uuid)
                 AND student_section_assignment_id=CAST(:assignment_id AS uuid)
                 AND organization_id=CAST(:organization_id AS uuid)
                 AND institution_id=CAST(:institution_id AS uuid)
               FOR UPDATE"""
        ),
        params={
            "session_id": str(class_session_id),
            "assignment_id": str(payload.student_section_assignment_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if existing is not None:
        record = session.get(AttendanceRecord, existing[0])
        assert record is not None
        same_value = (
            record.attendance_code_id == payload.attendance_code_id
            and int(record.minutes_late or 0) == payload.minutes_late
            and record.note == payload.note
        )
        if same_value:
            return AttendanceMutation(record=record, changed=False, event_type=None)
        if not _expected_state_matches(expected_state, record):
            raise HTTPException(status_code=409, detail="Attendance changed; refresh before correcting")
        if correction_reason not in {"DATA_ENTRY_ERROR", "EVIDENCE_CORRECTION", "OFFLINE_RECONCILIATION"}:
            raise HTTPException(status_code=422, detail="A bounded correction reason is required")
        if (assignment[3] != "ACTIVE" or assignment[6] != "ACTIVE") and not allow_historical_correction:
            raise HTTPException(status_code=403, detail="Historical attendance correction is not permitted")
        before = {
            "attendance_code_id": str(record.attendance_code_id),
            "minutes_late": int(record.minutes_late or 0),
            "note_changed": record.note != payload.note,
        }
        record.attendance_code_id = payload.attendance_code_id
        record.minutes_late = payload.minutes_late
        record.note = payload.note
        session.add(record)
        event_type = "student.attendance.updated"
        action = "ATTENDANCE_RECORD_UPDATED"
        after = {
            "attendance_code_id": str(payload.attendance_code_id),
            "minutes_late": payload.minutes_late,
            "note_changed": before["note_changed"],
        }
    else:
        if not _expected_empty_state(expected_state):
            raise HTTPException(status_code=409, detail="Attendance state changed; refresh before retrying")
        if assignment[3] != "ACTIVE" or assignment[6] != "ACTIVE" or assignment[0] != "ACTIVE":
            raise HTTPException(status_code=403, detail="Student is outside the current attendance scope")
        record = AttendanceRecord(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            section_id=section_id,
            class_session_id=class_session_id,
            student_section_assignment_id=payload.student_section_assignment_id,
            attendance_code_id=payload.attendance_code_id,
            minutes_late=payload.minutes_late,
            note=payload.note,
        )
        session.add(record)
        event_type = "student.attendance.recorded"
        action = "ATTENDANCE_RECORD_RECORDED"
        before = None
        after = {
            "attendance_code_id": str(payload.attendance_code_id),
            "minutes_late": payload.minutes_late,
        }

    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action=action,
        entity_type="AttendanceRecord",
        entity_id=record.id,
        metadata={
            "class_session_id": str(class_session_id),
            "student_section_assignment_id": str(payload.student_section_assignment_id),
            "previous": before,
            "current": after,
            "reason": correction_reason if before is not None else None,
            "source": source,
        },
    )
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="attendance_record",
        aggregate_id=record.id,
        actor_user_id=principal.user_id,
        correlation_id=correlation_id,
        payload={
            "student_profile_id": str(assignment[4]),
            "student_section_assignment_id": str(payload.student_section_assignment_id),
            "class_session_id": str(class_session_id),
            "section_id": str(section_id),
            "attendance_code_id": str(payload.attendance_code_id),
            "minutes_late": payload.minutes_late,
        },
        metadata={"source": source, "reason": correction_reason},
    )
    session.flush()
    if commit:
        session.commit()
        session.refresh(record)
    return AttendanceMutation(record=record, changed=True, event_type=event_type)


def upsert_record(
    session: Session,
    principal: CurrentPrincipal,
    class_session_id: UUID,
    payload: AttendanceRecordUpsert,
    *,
    allow_historical_correction: bool = False,
    commit: bool = True,
):
    result = apply_attendance_record(
        session,
        principal,
        class_session_id,
        payload,
        expected_state=payload.expected_state,
        correction_reason=payload.correction_reason,
        source="m3_attendance_api",
        allow_historical_correction=allow_historical_correction,
        commit=commit,
    )
    return result.record
