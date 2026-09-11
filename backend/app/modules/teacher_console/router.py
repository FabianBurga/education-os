from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.access import (
    TeacherPrincipal,
    require_teacher_attendance,
    require_teacher_classes,
    require_teacher_grades,
    require_teacher_tasks,
)
from app.db.session import get_session
from app.modules.attendance.schemas import AttendanceRecordRead
from app.modules.automation.schemas import AutomationTaskRead
from app.modules.grades.schemas import GradeEntryRead
from app.modules.teacher_console.schemas import (
    TeacherAlert,
    TeacherAssessmentCreate,
    TeacherAssessmentRead,
    TeacherAttendanceCode,
    TeacherAttendanceMark,
    TeacherAttendanceRow,
    TeacherCategoryCreate,
    TeacherCategoryRead,
    TeacherClassRead,
    TeacherClassSession,
    TeacherGradeMark,
    TeacherGradeRow,
    TeacherGradingPeriod,
    TeacherRosterStudent,
    TeacherSessionCreate,
    TeacherSummary,
    TeacherTaskComplete,
    TeacherTaskRead,
)
from app.modules.teacher_console.service import (
    acknowledge_teacher_task,
    attendance_rows,
    complete_teacher_task,
    create_teacher_assessment,
    create_teacher_category,
    create_teacher_session,
    grade_rows,
    grading_periods,
    list_assessments,
    list_attendance_codes,
    list_categories,
    list_class_sessions,
    list_roster,
    list_teacher_alerts,
    list_teacher_classes,
    list_teacher_tasks,
    mark_attendance,
    mark_grade,
    teacher_summary,
)

router = APIRouter(prefix="/teacher", tags=["teacher-console"])
SessionDep = Annotated[Session, Depends(get_session)]
ClassPrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_classes),
]
AttendancePrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_attendance),
]
GradesPrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_grades),
]
TasksPrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_tasks),
]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def teacher_dashboard_html():
    path = Path(__file__).with_name("teacher_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/summary", response_model=TeacherSummary)
def summary(principal: ClassPrincipalDep, session: SessionDep):
    return teacher_summary(session, principal)


@router.get("/classes", response_model=list[TeacherClassRead])
def classes(principal: ClassPrincipalDep, session: SessionDep):
    return list_teacher_classes(session, principal)


@router.get(
    "/classes/{course_offering_id}/roster",
    response_model=list[TeacherRosterStudent],
)
def roster(
    course_offering_id: UUID,
    principal: ClassPrincipalDep,
    session: SessionDep,
):
    return list_roster(
        session,
        principal,
        course_offering_id,
    )


@router.get(
    "/alerts",
    response_model=list[TeacherAlert],
)
def alerts(principal: ClassPrincipalDep, session: SessionDep):
    return list_teacher_alerts(session, principal)


@router.get(
    "/attendance/codes",
    response_model=list[TeacherAttendanceCode],
)
def attendance_codes(
    _: AttendancePrincipalDep,
    session: SessionDep,
):
    return list_attendance_codes(session)


@router.get(
    "/classes/{course_offering_id}/sessions",
    response_model=list[TeacherClassSession],
)
def class_sessions(
    course_offering_id: UUID,
    principal: AttendancePrincipalDep,
    session: SessionDep,
):
    return list_class_sessions(
        session,
        principal,
        course_offering_id,
    )


@router.post(
    "/classes/{course_offering_id}/sessions",
    response_model=TeacherClassSession,
    status_code=201,
)
def class_session_create(
    course_offering_id: UUID,
    payload: TeacherSessionCreate,
    principal: AttendancePrincipalDep,
    session: SessionDep,
):
    return create_teacher_session(
        session,
        principal,
        course_offering_id,
        payload,
    )


@router.get(
    "/sessions/{class_session_id}/attendance",
    response_model=list[TeacherAttendanceRow],
)
def session_attendance(
    class_session_id: UUID,
    principal: AttendancePrincipalDep,
    session: SessionDep,
):
    return attendance_rows(
        session,
        principal,
        class_session_id,
    )


@router.put(
    "/sessions/{class_session_id}/attendance",
    response_model=AttendanceRecordRead,
)
def session_attendance_mark(
    class_session_id: UUID,
    payload: TeacherAttendanceMark,
    principal: AttendancePrincipalDep,
    session: SessionDep,
):
    return mark_attendance(
        session,
        principal,
        class_session_id,
        payload,
    )


@router.get(
    "/classes/{course_offering_id}/grading-periods",
    response_model=list[TeacherGradingPeriod],
)
def class_grading_periods(
    course_offering_id: UUID,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return grading_periods(
        session,
        principal,
        course_offering_id,
    )


@router.get(
    "/classes/{course_offering_id}/categories",
    response_model=list[TeacherCategoryRead],
)
def class_categories(
    course_offering_id: UUID,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return list_categories(
        session,
        principal,
        course_offering_id,
    )


@router.post(
    "/classes/{course_offering_id}/categories",
    response_model=TeacherCategoryRead,
    status_code=201,
)
def class_category_create(
    course_offering_id: UUID,
    payload: TeacherCategoryCreate,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return create_teacher_category(
        session,
        principal,
        course_offering_id,
        payload,
    )


@router.get(
    "/classes/{course_offering_id}/assessments",
    response_model=list[TeacherAssessmentRead],
)
def class_assessments(
    course_offering_id: UUID,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return list_assessments(
        session,
        principal,
        course_offering_id,
    )


@router.post(
    "/classes/{course_offering_id}/assessments",
    response_model=TeacherAssessmentRead,
    status_code=201,
)
def class_assessment_create(
    course_offering_id: UUID,
    payload: TeacherAssessmentCreate,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return create_teacher_assessment(
        session,
        principal,
        course_offering_id,
        payload,
    )


@router.get(
    "/assessments/{assessment_id}/grades",
    response_model=list[TeacherGradeRow],
)
def assessment_grades(
    assessment_id: UUID,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return grade_rows(
        session,
        principal,
        assessment_id,
    )


@router.put(
    "/assessments/{assessment_id}/grades",
    response_model=GradeEntryRead,
)
def assessment_grade_mark(
    assessment_id: UUID,
    payload: TeacherGradeMark,
    principal: GradesPrincipalDep,
    session: SessionDep,
):
    return mark_grade(
        session,
        principal,
        assessment_id,
        payload,
    )


@router.get("/tasks", response_model=list[TeacherTaskRead])
def tasks(
    principal: TasksPrincipalDep,
    session: SessionDep,
):
    return list_teacher_tasks(session, principal)


@router.post(
    "/tasks/{task_id}/acknowledge",
    response_model=AutomationTaskRead,
)
def task_acknowledge(
    task_id: UUID,
    principal: TasksPrincipalDep,
    session: SessionDep,
):
    return acknowledge_teacher_task(
        session,
        principal,
        task_id,
    )


@router.post(
    "/tasks/{task_id}/complete",
    response_model=AutomationTaskRead,
)
def task_complete(
    task_id: UUID,
    payload: TeacherTaskComplete,
    principal: TasksPrincipalDep,
    session: SessionDep,
):
    return complete_teacher_task(
        session,
        principal,
        task_id,
        payload,
    )
