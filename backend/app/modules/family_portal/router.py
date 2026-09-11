from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.access import GuardianPrincipalDep
from app.db.session import get_session
from app.modules.family_portal.schemas import (
    AttendanceItem,
    ChildCard,
    ChildOverview,
    FamilyNoticeRead,
    GradeItem,
    GuardianMe,
    NoticeAcknowledgeResult,
)
from app.modules.family_portal.service import (
    acknowledge_notice,
    child_attendance,
    child_grades,
    child_overview,
    children,
    guardian_me,
    list_portal_notices,
)

router = APIRouter(prefix="/family-portal", tags=["family-portal"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/me", response_model=GuardianMe)
def portal_me(guardian: GuardianPrincipalDep, session: SessionDep):
    return guardian_me(session, guardian)


@router.get("/children", response_model=list[ChildCard])
def portal_children(guardian: GuardianPrincipalDep, session: SessionDep):
    return children(session, guardian)


@router.get("/children/{student_profile_id}/overview", response_model=ChildOverview)
def portal_child_overview(
    student_profile_id: UUID,
    guardian: GuardianPrincipalDep,
    session: SessionDep,
):
    return child_overview(session, guardian, student_profile_id)


@router.get(
    "/children/{student_profile_id}/attendance",
    response_model=list[AttendanceItem],
)
def portal_child_attendance(
    student_profile_id: UUID,
    guardian: GuardianPrincipalDep,
    session: SessionDep,
    limit: int = Query(default=30, ge=1, le=200),
):
    return child_attendance(session, guardian, student_profile_id, limit)


@router.get(
    "/children/{student_profile_id}/grades",
    response_model=list[GradeItem],
)
def portal_child_grades(
    student_profile_id: UUID,
    guardian: GuardianPrincipalDep,
    session: SessionDep,
):
    return child_grades(session, guardian, student_profile_id)


@router.get("/notices", response_model=list[FamilyNoticeRead])
def portal_notices(guardian: GuardianPrincipalDep, session: SessionDep):
    return list_portal_notices(session, guardian)


@router.post(
    "/notices/{notice_id}/acknowledge",
    response_model=NoticeAcknowledgeResult,
)
def portal_notice_acknowledge(
    notice_id: UUID,
    guardian: GuardianPrincipalDep,
    session: SessionDep,
):
    return acknowledge_notice(session, guardian, notice_id)


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def portal_dashboard():
    path = Path(__file__).with_name("family_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))
