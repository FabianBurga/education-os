from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
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
)
from app.modules.attendance.service import (
    create_code,
    create_session,
    list_codes,
    list_records,
    list_sessions,
    upsert_record,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/codes", response_model=list[AttendanceCodeRead])
def codes_list(_: PrincipalDep, session: SessionDep):
    return list_codes(session)


@router.post("/codes", response_model=AttendanceCodeRead, status_code=201)
def codes_create(
    payload: AttendanceCodeCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_code(session, principal, payload)


@router.get("/sessions", response_model=list[ClassSessionRead])
def sessions_list(_: PrincipalDep, session: SessionDep):
    return list_sessions(session)


@router.post("/sessions", response_model=ClassSessionRead, status_code=201)
def sessions_create(
    payload: ClassSessionCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_session(session, principal, payload)


@router.get(
    "/sessions/{class_session_id}/records",
    response_model=list[AttendanceRecordRead],
)
def records_list(
    class_session_id: UUID,
    _: PrincipalDep,
    session: SessionDep,
):
    return list_records(session, class_session_id)


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
    return upsert_record(session, principal, class_session_id, payload)
