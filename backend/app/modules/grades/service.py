from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.academics.models import CourseOffering, StudentSectionAssignment
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.events.service import enqueue_canonical_event
from app.modules.grades.models import (
    Assessment,
    AssessmentCategory,
    GradeEntry,
    GradingPeriod,
    GradingScale,
    GradingScaleBand,
)
from app.modules.grades.schemas import (
    AssessmentCategoryCreate,
    AssessmentCreate,
    GradeEntryUpsert,
    GradingPeriodCreate,
    GradingScaleBandCreate,
    GradingScaleCreate,
)


def _get(session: Session, model, entity_id: UUID, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found in current tenant")
    return entity


def list_periods(session: Session):
    return session.exec(
        select(GradingPeriod).order_by(GradingPeriod.sequence, GradingPeriod.starts_on)
    ).all()


def create_period(
    session: Session,
    principal: CurrentPrincipal,
    payload: GradingPeriodCreate,
):
    academic_period = _get(
        session,
        AcademicPeriod,
        payload.academic_period_id,
        "Academic period",
    )
    if payload.starts_on < academic_period.starts_on or payload.ends_on > academic_period.ends_on:
        raise HTTPException(
            status_code=409,
            detail="Grading period must be inside the academic period",
        )
    entity = GradingPeriod(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_scales(session: Session):
    return session.exec(select(GradingScale).order_by(GradingScale.name)).all()


def create_scale(
    session: Session,
    principal: CurrentPrincipal,
    payload: GradingScaleCreate,
):
    entity = GradingScale(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def add_scale_band(
    session: Session,
    principal: CurrentPrincipal,
    scale_id: UUID,
    payload: GradingScaleBandCreate,
):
    scale = _get(session, GradingScale, scale_id, "Grading scale")
    if payload.minimum_score < scale.minimum_score or payload.maximum_score > scale.maximum_score:
        raise HTTPException(
            status_code=409,
            detail="Scale band must fit inside grading scale range",
        )
    entity = GradingScaleBand(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        grading_scale_id=scale_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_categories(session: Session):
    return session.exec(select(AssessmentCategory).order_by(AssessmentCategory.created_at)).all()


def create_category(
    session: Session,
    principal: CurrentPrincipal,
    payload: AssessmentCategoryCreate,
):
    offering = _get(session, CourseOffering, payload.course_offering_id, "Course offering")
    _get(session, GradingPeriod, payload.grading_period_id, "Grading period")
    entity = AssessmentCategory(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=offering.section_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_assessments(session: Session):
    return session.exec(select(Assessment).order_by(Assessment.created_at.desc())).all()


def create_assessment(
    session: Session,
    principal: CurrentPrincipal,
    payload: AssessmentCreate,
):
    offering = _get(session, CourseOffering, payload.course_offering_id, "Course offering")
    _get(session, GradingPeriod, payload.grading_period_id, "Grading period")
    category = _get(
        session,
        AssessmentCategory,
        payload.assessment_category_id,
        "Assessment category",
    )
    if category.course_offering_id != offering.id:
        raise HTTPException(
            status_code=409,
            detail="Assessment category belongs to another course offering",
        )
    if category.grading_period_id != payload.grading_period_id:
        raise HTTPException(
            status_code=409,
            detail="Assessment category belongs to another grading period",
        )

    entity = Assessment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=offering.section_id,
        **payload.model_dump(),
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def list_entries(session: Session, assessment_id: UUID):
    _get(session, Assessment, assessment_id, "Assessment")
    return session.exec(
        select(GradeEntry)
        .where(GradeEntry.assessment_id == assessment_id)
        .order_by(GradeEntry.created_at)
    ).all()


def upsert_entry(
    session: Session,
    principal: CurrentPrincipal,
    assessment_id: UUID,
    payload: GradeEntryUpsert,
):
    assessment = _get(session, Assessment, assessment_id, "Assessment")
    assignment = _get(
        session,
        StudentSectionAssignment,
        payload.student_section_assignment_id,
        "Student section assignment",
    )
    enrollment = _get(session, Enrollment, assignment.enrollment_id, "Enrollment")

    if assignment.section_id != assessment.section_id:
        raise HTTPException(
            status_code=409,
            detail="Student is not assigned to the assessment section",
        )
    if payload.score is not None and payload.score > assessment.max_score:
        raise HTTPException(
            status_code=422,
            detail="Score cannot exceed assessment max_score",
        )
    if payload.status == "GRADED" and payload.score is None:
        raise HTTPException(
            status_code=422,
            detail="GRADED entries require a score",
        )

    existing = session.exec(
        select(GradeEntry).where(
            GradeEntry.assessment_id == assessment_id,
            GradeEntry.student_section_assignment_id
            == payload.student_section_assignment_id,
        )
    ).first()

    if existing:
        existing.score = payload.score
        existing.status = payload.status
        existing.feedback = payload.feedback
        session.add(existing)
        enqueue_canonical_event(
            session,
            institution_id=principal.institution_id,
            event_type="student.grade.updated",
            event_version=1,
            aggregate_type="grade_entry",
            aggregate_id=existing.id,
            actor_user_id=principal.user_id,
            payload={
                "student_profile_id": str(enrollment.student_profile_id),
                "student_section_assignment_id": str(assignment.id),
                "assessment_id": str(assessment.id),
                "section_id": str(assessment.section_id),
                "status": existing.status,
                "score": (
                    float(existing.score) if existing.score is not None else None
                ),
            },
        )
        session.commit()
        session.refresh(existing)
        return existing

    entity = GradeEntry(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=assessment.section_id,
        assessment_id=assessment_id,
        **payload.model_dump(),
    )
    session.add(entity)
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.grade.recorded",
        event_version=1,
        aggregate_type="grade_entry",
        aggregate_id=entity.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(enrollment.student_profile_id),
            "student_section_assignment_id": str(assignment.id),
            "assessment_id": str(assessment.id),
            "section_id": str(assessment.section_id),
            "status": entity.status,
            "score": float(entity.score) if entity.score is not None else None,
        },
    )
    session.commit()
    session.refresh(entity)
    return entity
