from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db.session import get_session
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
from app.modules.guardian_console.security import (
    GuardianAccessDep,
    GuardianAttendanceDep,
    GuardianGradesDep,
    GuardianNoticeAckDep,
    GuardianNoticesDep,
    GuardianProgressDep,
    GuardianScheduleDep,
    GuardianStudentsDep,
)
from app.modules.guardian_console.service import (
    acknowledge_guardian_notice,
    guardian_me,
    guardian_notices,
    guardian_student_attendance,
    guardian_student_classes,
    guardian_student_grades,
    guardian_student_pending,
    guardian_student_progress,
    guardian_student_schedule,
    guardian_student_summary,
    guardian_students,
)

router = APIRouter(prefix="/guardian", tags=["guardian-console"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def guardian_dashboard_html():
    path = Path(__file__).with_name("guardian_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/me", response_model=GuardianConsoleMe)
def me(guardian: GuardianAccessDep, session: SessionDep):
    return guardian_me(session, guardian)


@router.get("/students", response_model=list[GuardianStudentCard])
def students(guardian: GuardianStudentsDep, session: SessionDep):
    return guardian_students(session, guardian)


@router.get(
    "/students/{student_profile_id}/summary",
    response_model=GuardianStudentSummary,
)
def student_summary(
    student_profile_id: UUID,
    guardian: GuardianStudentsDep,
    session: SessionDep,
):
    return guardian_student_summary(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/classes",
    response_model=list[GuardianClassRead],
)
def student_classes(
    student_profile_id: UUID,
    guardian: GuardianStudentsDep,
    session: SessionDep,
):
    return guardian_student_classes(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/schedule",
    response_model=list[GuardianScheduleRead],
)
def student_schedule(
    student_profile_id: UUID,
    guardian: GuardianScheduleDep,
    session: SessionDep,
):
    return guardian_student_schedule(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/attendance",
    response_model=list[GuardianAttendanceRead],
)
def student_attendance(
    student_profile_id: UUID,
    guardian: GuardianAttendanceDep,
    session: SessionDep,
):
    return guardian_student_attendance(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/grades",
    response_model=list[GuardianGradeRead],
)
def student_grades(
    student_profile_id: UUID,
    guardian: GuardianGradesDep,
    session: SessionDep,
):
    return guardian_student_grades(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/pending",
    response_model=list[GuardianPendingRead],
)
def student_pending(
    student_profile_id: UUID,
    guardian: GuardianGradesDep,
    session: SessionDep,
):
    return guardian_student_pending(
        session,
        guardian,
        student_profile_id,
    )


@router.get(
    "/students/{student_profile_id}/progress",
    response_model=list[GuardianProgressRead],
)
def student_progress(
    student_profile_id: UUID,
    guardian: GuardianProgressDep,
    session: SessionDep,
):
    return guardian_student_progress(
        session,
        guardian,
        student_profile_id,
    )


@router.get("/notices", response_model=list[GuardianNoticeRead])
def notices(
    guardian: GuardianNoticesDep,
    session: SessionDep,
):
    return guardian_notices(session, guardian)


@router.post(
    "/notices/{notice_id}/acknowledge",
    response_model=GuardianNoticeAcknowledge,
)
def notice_acknowledge(
    notice_id: UUID,
    guardian: GuardianNoticeAckDep,
    session: SessionDep,
):
    return acknowledge_guardian_notice(
        session,
        guardian,
        notice_id,
    )
