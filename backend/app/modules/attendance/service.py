from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.academics.models import (
    CourseOffering,
    ScheduleSlot,
    StudentSectionAssignment,
)
from app.modules.attendance.models import AttendanceCode, AttendanceRecord, ClassSession
from app.modules.attendance.schemas import (
    AttendanceCodeCreate,
    AttendanceRecordUpsert,
    ClassSessionCreate,
)


def _get(session: Session, model, entity_id: UUID, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found in current tenant")
    return entity


def list_codes(session: Session):
    return session.exec(select(AttendanceCode).order_by(AttendanceCode.code)).all()


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


def list_sessions(session: Session):
    return session.exec(
        select(ClassSession).order_by(
            ClassSession.session_date.desc(),
            ClassSession.starts_at.desc(),
        )
    ).all()


def create_session(
    session: Session,
    principal: CurrentPrincipal,
    payload: ClassSessionCreate,
):
    offering = _get(session, CourseOffering, payload.course_offering_id, "Course offering")
    if payload.schedule_slot_id:
        slot = _get(session, ScheduleSlot, payload.schedule_slot_id, "Schedule slot")
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


def list_records(session: Session, class_session_id: UUID):
    _get(session, ClassSession, class_session_id, "Class session")
    return session.exec(
        select(AttendanceRecord)
        .where(AttendanceRecord.class_session_id == class_session_id)
        .order_by(AttendanceRecord.created_at)
    ).all()


def upsert_record(
    session: Session,
    principal: CurrentPrincipal,
    class_session_id: UUID,
    payload: AttendanceRecordUpsert,
):
    class_session = _get(session, ClassSession, class_session_id, "Class session")
    assignment = _get(
        session,
        StudentSectionAssignment,
        payload.student_section_assignment_id,
        "Student section assignment",
    )
    _get(session, AttendanceCode, payload.attendance_code_id, "Attendance code")

    if assignment.section_id != class_session.section_id:
        raise HTTPException(
            status_code=409,
            detail="Student is not assigned to the class session section",
        )

    existing = session.exec(
        select(AttendanceRecord).where(
            AttendanceRecord.class_session_id == class_session_id,
            AttendanceRecord.student_section_assignment_id == payload.student_section_assignment_id,
        )
    ).first()

    if existing:
        existing.attendance_code_id = payload.attendance_code_id
        existing.minutes_late = payload.minutes_late
        existing.note = payload.note
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    entity = AttendanceRecord(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=class_session.section_id,
        class_session_id=class_session_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity
