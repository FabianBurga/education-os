from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.academics.models import (
    AcademicLevel,
    CourseOffering,
    CurriculumPlan,
    CurriculumSubject,
    GradeLevel,
    ScheduleSlot,
    Section,
    StudentSectionAssignment,
    Subject,
    TeachingAssignment,
)
from app.modules.academics.schemas import (
    AcademicLevelCreate,
    CourseOfferingCreate,
    CurriculumPlanCreate,
    CurriculumSubjectCreate,
    GradeLevelCreate,
    ScheduleSlotCreate,
    SectionCreate,
    StudentSectionAssignmentCreate,
    SubjectCreate,
    TeachingAssignmentCreate,
)
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.families.models import StaffProfile


def _get(session: Session, model, entity_id: UUID, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found in current tenant")
    return entity


def _campus_exists(session: Session, campus_id: UUID) -> bool:
    row = session.exec(
        text("SELECT id FROM campuses WHERE id = :campus_id").bindparams(campus_id=campus_id)
    ).first()
    return row is not None


def list_levels(session: Session):
    return session.exec(
        select(AcademicLevel).order_by(AcademicLevel.sort_order, AcademicLevel.name)
    ).all()


def create_level(session: Session, principal: CurrentPrincipal, payload: AcademicLevelCreate):
    entity = AcademicLevel(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_grades(session: Session):
    return session.exec(select(GradeLevel).order_by(GradeLevel.sort_order, GradeLevel.name)).all()


def create_grade(session: Session, principal: CurrentPrincipal, payload: GradeLevelCreate):
    _get(session, AcademicLevel, payload.academic_level_id, "Academic level")
    entity = GradeLevel(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_subjects(session: Session):
    return session.exec(select(Subject).order_by(Subject.name)).all()


def create_subject(session: Session, principal: CurrentPrincipal, payload: SubjectCreate):
    entity = Subject(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_sections(session: Session):
    return session.exec(select(Section).order_by(Section.name)).all()


def create_section(session: Session, principal: CurrentPrincipal, payload: SectionCreate):
    period = _get(session, AcademicPeriod, payload.academic_period_id, "Academic period")
    if period.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Academic period is closed")
    _get(session, GradeLevel, payload.grade_level_id, "Grade level")
    if not _campus_exists(session, payload.campus_id):
        raise HTTPException(status_code=404, detail="Campus not found in current tenant")
    entity = Section(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_curriculum_plans(session: Session):
    return session.exec(select(CurriculumPlan).order_by(CurriculumPlan.name)).all()


def create_curriculum_plan(
    session: Session,
    principal: CurrentPrincipal,
    payload: CurriculumPlanCreate,
):
    _get(session, AcademicPeriod, payload.academic_period_id, "Academic period")
    _get(session, GradeLevel, payload.grade_level_id, "Grade level")
    entity = CurriculumPlan(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def add_curriculum_subject(
    session: Session,
    principal: CurrentPrincipal,
    plan_id: UUID,
    payload: CurriculumSubjectCreate,
):
    _get(session, CurriculumPlan, plan_id, "Curriculum plan")
    _get(session, Subject, payload.subject_id, "Subject")
    entity = CurriculumSubject(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        curriculum_plan_id=plan_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_course_offerings(session: Session):
    return session.exec(select(CourseOffering).order_by(CourseOffering.created_at)).all()


def create_course_offering(
    session: Session,
    principal: CurrentPrincipal,
    payload: CourseOfferingCreate,
):
    section = _get(session, Section, payload.section_id, "Section")
    _get(session, Subject, payload.subject_id, "Subject")
    if payload.curriculum_subject_id:
        curriculum_subject = _get(
            session,
            CurriculumSubject,
            payload.curriculum_subject_id,
            "Curriculum subject",
        )
        if curriculum_subject.subject_id != payload.subject_id:
            raise HTTPException(
                status_code=409,
                detail="Curriculum subject and course subject do not match",
            )
    entity = CourseOffering(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        academic_period_id=section.academic_period_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def create_teaching_assignment(
    session: Session,
    principal: CurrentPrincipal,
    payload: TeachingAssignmentCreate,
):
    _get(session, CourseOffering, payload.course_offering_id, "Course offering")
    _get(session, StaffProfile, payload.staff_profile_id, "Staff profile")
    entity = TeachingAssignment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def create_student_section_assignment(
    session: Session,
    principal: CurrentPrincipal,
    payload: StudentSectionAssignmentCreate,
):
    enrollment = _get(session, Enrollment, payload.enrollment_id, "Enrollment")
    section = _get(session, Section, payload.section_id, "Section")
    if enrollment.academic_period_id != section.academic_period_id:
        raise HTTPException(
            status_code=409,
            detail="Enrollment and section belong to different academic periods",
        )
    entity = StudentSectionAssignment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        academic_period_id=section.academic_period_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_student_section_assignments(session: Session):
    return session.exec(
        select(StudentSectionAssignment).order_by(StudentSectionAssignment.created_at)
    ).all()


def create_schedule_slot(
    session: Session,
    principal: CurrentPrincipal,
    payload: ScheduleSlotCreate,
):
    _get(session, CourseOffering, payload.course_offering_id, "Course offering")
    entity = ScheduleSlot(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_schedule_slots(session: Session):
    return session.exec(
        select(ScheduleSlot).order_by(ScheduleSlot.weekday, ScheduleSlot.starts_at)
    ).all()
