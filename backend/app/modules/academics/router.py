from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.academics.schemas import (
    AcademicLevelCreate,
    AcademicLevelRead,
    CourseOfferingCreate,
    CourseOfferingRead,
    CurriculumPlanCreate,
    CurriculumPlanRead,
    CurriculumSubjectCreate,
    CurriculumSubjectRead,
    GradeLevelCreate,
    GradeLevelRead,
    ScheduleSlotCreate,
    ScheduleSlotRead,
    SectionCreate,
    SectionRead,
    StudentSectionAssignmentCreate,
    StudentSectionAssignmentRead,
    SubjectCreate,
    SubjectRead,
    TeachingAssignmentCreate,
    TeachingAssignmentRead,
)
from app.modules.academics.service import (
    add_curriculum_subject,
    create_course_offering,
    create_curriculum_plan,
    create_grade,
    create_level,
    create_schedule_slot,
    create_section,
    create_student_section_assignment,
    create_subject,
    create_teaching_assignment,
    list_academic_options,
    list_assignment_options,
    list_course_offerings,
    list_curriculum_plans,
    list_curriculum_subjects,
    list_grades,
    list_levels,
    list_schedule_slots,
    list_sections,
    list_student_section_assignments,
    list_subjects,
    list_teaching_assignments,
)

router = APIRouter(prefix="/academics", tags=["academic-core"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


class AcademicOption(BaseModel):
    id: UUID
    code: str
    name: str
    starts_on: date | None = None
    ends_on: date | None = None
    status: str | None = None


class CampusOption(BaseModel):
    id: UUID
    name: str


class AcademicOptionsRead(BaseModel):
    periods: list[AcademicOption]
    campuses: list[CampusOption]


class AssignmentOption(BaseModel):
    id: UUID
    label: str


@router.get("/options", response_model=AcademicOptionsRead)
def academic_options(principal: PrincipalDep, session: SessionDep):
    options = list_academic_options(session, principal)
    return AcademicOptionsRead(
        periods=[AcademicOption.model_validate(period, from_attributes=True) for period in options["periods"]],
        campuses=[CampusOption.model_validate(campus, from_attributes=True) for campus in options["campuses"]],
    )


@router.get("/assignment-options", response_model=list[AssignmentOption])
def assignment_options(principal: PrincipalDep, session: SessionDep):
    return list_assignment_options(session, principal)


@router.get("/levels", response_model=list[AcademicLevelRead])
def levels_list(_: PrincipalDep, session: SessionDep):
    return list_levels(session, _)


@router.post("/levels", response_model=AcademicLevelRead, status_code=201)
def levels_create(payload: AcademicLevelCreate, principal: PrincipalDep, session: SessionDep):
    return create_level(session, principal, payload)


@router.get("/grades", response_model=list[GradeLevelRead])
def grades_list(_: PrincipalDep, session: SessionDep):
    return list_grades(session, _)


@router.post("/grades", response_model=GradeLevelRead, status_code=201)
def grades_create(payload: GradeLevelCreate, principal: PrincipalDep, session: SessionDep):
    return create_grade(session, principal, payload)


@router.get("/subjects", response_model=list[SubjectRead])
def subjects_list(_: PrincipalDep, session: SessionDep):
    return list_subjects(session, _)


@router.post("/subjects", response_model=SubjectRead, status_code=201)
def subjects_create(payload: SubjectCreate, principal: PrincipalDep, session: SessionDep):
    return create_subject(session, principal, payload)


@router.get("/sections", response_model=list[SectionRead])
def sections_list(_: PrincipalDep, session: SessionDep):
    return list_sections(session, _)


@router.post("/sections", response_model=SectionRead, status_code=201)
def sections_create(payload: SectionCreate, principal: PrincipalDep, session: SessionDep):
    return create_section(session, principal, payload)


@router.get("/curriculum-plans", response_model=list[CurriculumPlanRead])
def curriculum_plans_list(_: PrincipalDep, session: SessionDep):
    return list_curriculum_plans(session, _)


@router.post("/curriculum-plans", response_model=CurriculumPlanRead, status_code=201)
def curriculum_plans_create(
    payload: CurriculumPlanCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_curriculum_plan(session, principal, payload)


@router.post(
    "/curriculum-plans/{plan_id}/subjects",
    response_model=CurriculumSubjectRead,
    status_code=201,
)
def curriculum_subjects_add(
    plan_id: UUID,
    payload: CurriculumSubjectCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return add_curriculum_subject(session, principal, plan_id, payload)


@router.get(
    "/curriculum-plans/{plan_id}/subjects",
    response_model=list[CurriculumSubjectRead],
)
def curriculum_subjects_list(plan_id: UUID, principal: PrincipalDep, session: SessionDep):
    return list_curriculum_subjects(session, principal, plan_id)


@router.get("/course-offerings", response_model=list[CourseOfferingRead])
def course_offerings_list(_: PrincipalDep, session: SessionDep):
    return list_course_offerings(session, _)


@router.post("/course-offerings", response_model=CourseOfferingRead, status_code=201)
def course_offerings_create(
    payload: CourseOfferingCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_course_offering(session, principal, payload)


@router.post(
    "/teaching-assignments",
    response_model=TeachingAssignmentRead,
    status_code=201,
)
def teaching_assignments_create(
    payload: TeachingAssignmentCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_teaching_assignment(session, principal, payload)


@router.get("/teaching-assignments", response_model=list[TeachingAssignmentRead])
def teaching_assignments_list(principal: PrincipalDep, session: SessionDep):
    return list_teaching_assignments(session, principal)


@router.get(
    "/student-section-assignments",
    response_model=list[StudentSectionAssignmentRead],
)
def student_section_assignments_list(_: PrincipalDep, session: SessionDep):
    return list_student_section_assignments(session, _)


@router.post(
    "/student-section-assignments",
    response_model=StudentSectionAssignmentRead,
    status_code=201,
)
def student_section_assignments_create(
    payload: StudentSectionAssignmentCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_student_section_assignment(session, principal, payload)


@router.get("/schedule-slots", response_model=list[ScheduleSlotRead])
def schedule_slots_list(_: PrincipalDep, session: SessionDep):
    return list_schedule_slots(session, _)


@router.post("/schedule-slots", response_model=ScheduleSlotRead, status_code=201)
def schedule_slots_create(
    payload: ScheduleSlotCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_schedule_slot(session, principal, payload)
