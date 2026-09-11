from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.access import (
    StudentPrincipal,
    require_student_attendance,
    require_student_classes,
    require_student_grades,
    require_student_notices,
    require_student_profile,
    require_student_progress,
    require_student_schedule,
)
from app.db.session import get_session
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
from app.modules.student_console.service import (
    student_attendance,
    student_classes,
    student_grades,
    student_notices,
    student_pending,
    student_profile,
    student_progress,
    student_schedule,
    student_summary,
)

router = APIRouter(prefix="/student", tags=["student-console"])
SessionDep = Annotated[Session, Depends(get_session)]
ProfileDep = Annotated[
    StudentPrincipal,
    Depends(require_student_profile),
]
ClassesDep = Annotated[
    StudentPrincipal,
    Depends(require_student_classes),
]
ScheduleDep = Annotated[
    StudentPrincipal,
    Depends(require_student_schedule),
]
AttendanceDep = Annotated[
    StudentPrincipal,
    Depends(require_student_attendance),
]
GradesDep = Annotated[
    StudentPrincipal,
    Depends(require_student_grades),
]
NoticesDep = Annotated[
    StudentPrincipal,
    Depends(require_student_notices),
]
ProgressDep = Annotated[
    StudentPrincipal,
    Depends(require_student_progress),
]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def student_dashboard_html():
    path = Path(__file__).with_name("student_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/me", response_model=StudentProfileRead)
def me(principal: ProfileDep, session: SessionDep):
    return student_profile(session, principal)


@router.get("/summary", response_model=StudentSummary)
def summary(principal: ProgressDep, session: SessionDep):
    return student_summary(session, principal)


@router.get("/classes", response_model=list[StudentClassRead])
def classes(principal: ClassesDep, session: SessionDep):
    return student_classes(session, principal)


@router.get("/schedule", response_model=list[StudentScheduleRead])
def schedule(principal: ScheduleDep, session: SessionDep):
    return student_schedule(session, principal)


@router.get("/attendance", response_model=list[StudentAttendanceRead])
def attendance(principal: AttendanceDep, session: SessionDep):
    return student_attendance(session, principal)


@router.get("/grades", response_model=list[StudentGradeRead])
def grades(principal: GradesDep, session: SessionDep):
    return student_grades(session, principal)


@router.get("/pending", response_model=list[StudentPendingRead])
def pending(principal: GradesDep, session: SessionDep):
    return student_pending(session, principal)


@router.get("/progress", response_model=list[StudentProgressRead])
def progress(principal: ProgressDep, session: SessionDep):
    return student_progress(session, principal)


@router.get("/notices", response_model=list[StudentNoticeRead])
def notices(principal: NoticesDep, session: SessionDep):
    return student_notices(session, principal)
