from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.attendance.schemas import (
    AttendanceCodeCreate,
    AttendanceCodeRead,
    AttendanceRecordRead,
    AttendanceRecordUpsert,
    ClassSessionCreate,
    ClassSessionRead,
    ClassSessionStatusChange,
)
from app.modules.attendance.service import (
    change_class_session_status,
    create_code,
    create_session,
    list_codes,
    list_records,
    list_sessions,
    require_attendance_permission,
    upsert_record,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/codes", response_model=list[AttendanceCodeRead])
def codes_list(principal: PrincipalDep, session: SessionDep):
    require_attendance_permission(session, principal, "attendance.read")
    return list_codes(session, principal)


@router.post("/codes", response_model=AttendanceCodeRead, status_code=201)
def codes_create(
    payload: AttendanceCodeCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_attendance_permission(session, principal, "attendance.manage")
    return create_code(session, principal, payload)


@router.get("/sessions", response_model=list[ClassSessionRead])
def sessions_list(principal: PrincipalDep, session: SessionDep):
    require_attendance_permission(session, principal, "attendance.read")
    return list_sessions(session, principal)


@router.post("/sessions", response_model=ClassSessionRead, status_code=201)
def sessions_create(
    payload: ClassSessionCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_attendance_permission(session, principal, "attendance.manage")
    return create_session(session, principal, payload)


@router.patch("/sessions/{class_session_id}/status", response_model=ClassSessionRead)
def session_status_change(
    class_session_id: UUID,
    payload: ClassSessionStatusChange,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_attendance_permission(session, principal, "attendance.manage")
    return change_class_session_status(session, principal, class_session_id, payload)


@router.get(
    "/sessions/{class_session_id}/records",
    response_model=list[AttendanceRecordRead],
)
def records_list(
    class_session_id: UUID,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_attendance_permission(session, principal, "attendance.read")
    return list_records(session, principal, class_session_id)


@router.put(
    "/sessions/{class_session_id}/records",
    response_model=AttendanceRecordRead,
)
def records_upsert(
    class_session_id: UUID,
    payload: AttendanceRecordUpsert,
    principal: PrincipalDep,
    session: SessionDep,
):
    exists = session.exec(
        text(
            "SELECT 1 FROM attendance_records WHERE class_session_id=CAST(:session_id AS uuid) "
            "AND student_section_assignment_id=CAST(:assignment_id AS uuid) "
            "AND organization_id=CAST(:organization_id AS uuid) "
            "AND institution_id=CAST(:institution_id AS uuid) LIMIT 1"
        ),
        params={
            "session_id": str(class_session_id),
            "assignment_id": str(payload.student_section_assignment_id),
            "organization_id": str(principal.organization_id),
            "institution_id": str(principal.institution_id),
        },
    ).first()
    if exists is None:
        require_attendance_permission(session, principal, "attendance.manage")
    else:
        require_attendance_permission(session, principal, "attendance.read")
        require_attendance_permission(session, principal, "attendance.correct")
    return upsert_record(
        session,
        principal,
        class_session_id,
        payload,
        allow_historical_correction=exists is not None,
    )
