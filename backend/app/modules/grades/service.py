import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.access import TeacherPrincipal
from app.api.deps import CurrentPrincipal
from app.modules.academics.models import CourseOffering
from app.modules.academics.service import require_academic_permission
from app.modules.audit.models import AuditLog
from app.modules.audit.service import record_audit
from app.modules.enrollment.models import AcademicPeriod
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
    AssessmentStatusChange,
    GradeEntryHistoryRead,
    GradeEntryRead,
    GradeEntryUpsert,
    GradingPeriodCreate,
    GradingPeriodStatusChange,
    GradingScaleBandCreate,
    GradingScaleCreate,
)

_GRADE_AUDIT_ACTIONS = ("GRADE_RESULT_RECORDED", "GRADE_RESULT_CORRECTED")
_GRADE_OPERATION_ACTIONS = (*_GRADE_AUDIT_ACTIONS, "GRADE_RESULT_NOOP")
_VALID_RESULTS = {"PENDING", "GRADED", "MISSING", "EXCUSED"}


def _scope_query(session: Session, model, entity_id: UUID, principal: CurrentPrincipal, label: str, *, lock: bool = False):
    query = select(model).where(
        model.id == entity_id,
        model.organization_id == principal.organization_id,
        model.institution_id == principal.institution_id,
    )
    if lock:
        query = query.with_for_update()
    entity = session.exec(query).first()
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return entity


def _require_grade_access(
    session: Session,
    principal: CurrentPrincipal,
    *,
    manage: bool,
    course_offering_id: UUID | None = None,
) -> None:
    if not isinstance(principal, TeacherPrincipal):
        require_academic_permission(
            session,
            principal,
            "academics.manage" if manage else "academics.read",
        )
        return

    permission = session.exec(
        text(
            """SELECT 1 FROM memberships m
            JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN roles r ON r.id=mr.role_id AND r.institution_id=m.institution_id
            JOIN role_permissions rp ON rp.role_id=r.id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id=:user_id AND m.institution_id=:institution_id
              AND m.status='ACTIVE' AND p.key='teacher.grades.manage' LIMIT 1"""
        ),
        params={"user_id": principal.user_id, "institution_id": principal.institution_id},
    ).first()
    if permission is None:
        raise HTTPException(status_code=403, detail="Teacher grade-management permission required")
    if course_offering_id is None:
        raise HTTPException(status_code=403, detail="Teacher grade operations require an assigned course")
    staff_profile_id = principal.staff_profile_id
    if course_offering_id is not None:
        assignment = session.exec(
            text(
                """SELECT 1 FROM teaching_assignments ta
                JOIN course_offerings co ON co.id=ta.course_offering_id
                JOIN academic_periods ap ON ap.id=co.academic_period_id
                WHERE ta.course_offering_id=:offering_id
                  AND ta.staff_profile_id=:staff_id
                  AND ta.organization_id=:organization_id
                  AND ta.institution_id=:institution_id
                  AND co.organization_id=:organization_id
                  AND co.institution_id=:institution_id AND co.status='ACTIVE'
                  AND ap.status='ACTIVE'
                  AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE)
                  AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
                LIMIT 1"""
            ),
            params={
                "offering_id": course_offering_id,
                "staff_id": staff_profile_id,
                "organization_id": principal.organization_id,
                "institution_id": principal.institution_id,
            },
        ).first()
        if assignment is None:
            raise HTTPException(status_code=403, detail="Course offering is outside the current teacher scope")


def _operation_lock(session: Session, principal: CurrentPrincipal, namespace: str, operation_id: UUID) -> None:
    session.exec(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        params={
            "lock_key": f"{namespace}:{principal.institution_id}:{operation_id}"
        },
    )


def _grade_revision(session: Session, principal: CurrentPrincipal, grade_entry_id: UUID) -> int:
    return int(
        session.exec(
            text(
                """SELECT COALESCE(MAX((metadata_json->>'result_revision')::integer),0)
                FROM audit_logs
                WHERE institution_id=:institution_id AND entity_type='GradeEntry'
                  AND entity_id=:entity_id AND action IN ('GRADE_RESULT_RECORDED','GRADE_RESULT_CORRECTED')
                  AND metadata_json ? 'result_revision'"""
            ),
            params={"institution_id": principal.institution_id, "entity_id": grade_entry_id},
        ).one()[0]
    )


def _grade_value(entry: GradeEntry | None) -> dict | None:
    if entry is None:
        return None
    score = Decimal(str(entry.score)) if entry.score is not None else None
    return {
        "score": format(score.quantize(Decimal("0.001")), "f") if score is not None else None,
        "status": entry.status,
    }


def _grade_command_value(entry: GradeEntry | None) -> dict | None:
    value = _grade_value(entry)
    if value is None:
        return None
    return {**value, "feedback": entry.feedback}


def _grade_request_fingerprint(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _assessment_event(session: Session, principal: CurrentPrincipal, *, event_type: str, aggregate_id: UUID, payload: dict) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="assessment",
        aggregate_id=aggregate_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )


def _get(session: Session, model, entity_id: UUID, label: str, principal: CurrentPrincipal):
    return _scope_query(session, model, entity_id, principal, label)


def list_periods(session: Session, principal: CurrentPrincipal):
    _require_grade_access(session, principal, manage=False)
    return session.exec(
        select(GradingPeriod).where(
            GradingPeriod.organization_id == principal.organization_id,
            GradingPeriod.institution_id == principal.institution_id,
        ).order_by(GradingPeriod.sequence, GradingPeriod.starts_on)
    ).all()


def create_period(
    session: Session,
    principal: CurrentPrincipal,
    payload: GradingPeriodCreate,
):
    _require_grade_access(session, principal, manage=True)
    academic_period = _get(
        session,
        AcademicPeriod,
        payload.academic_period_id,
        "Academic period",
        principal,
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


def change_grading_period_status(
    session: Session,
    principal: CurrentPrincipal,
    period_id: UUID,
    payload: GradingPeriodStatusChange,
) -> GradingPeriod:
    _require_grade_access(session, principal, manage=True)
    period = _scope_query(session, GradingPeriod, period_id, principal, "Grading period", lock=True)
    if period.status != payload.expected_status:
        raise HTTPException(status_code=409, detail="Grading period status changed; reload and retry")
    allowed = {"PLANNED": "ACTIVE", "ACTIVE": "CLOSED"}
    if allowed.get(period.status) != payload.status:
        raise HTTPException(status_code=409, detail="Invalid grading period status transition")
    academic_period = _scope_query(session, AcademicPeriod, period.academic_period_id, principal, "Academic period")
    if payload.status == "ACTIVE" and academic_period.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Academic period must be active before its grading period")
    previous_status = period.status
    period.status = payload.status
    session.add(period)
    record_audit(
        session, institution_id=principal.institution_id,
        actor_user_id=principal.user_id, action="GRADING_PERIOD_STATUS_CHANGED",
        entity_type="GradingPeriod", entity_id=period.id,
        metadata={"academic_period_id": str(period.academic_period_id),
                  "previous_status": previous_status, "status": payload.status},
    )
    enqueue_canonical_event(
        session, institution_id=principal.institution_id,
        event_type="grading_period.status_changed", event_version=1,
        aggregate_type="grading_period", aggregate_id=period.id,
        actor_user_id=principal.user_id,
        payload={"grading_period_id": str(period.id),
                 "academic_period_id": str(period.academic_period_id),
                 "previous_status": previous_status, "status": payload.status},
    )
    session.commit()
    session.refresh(period)
    return period


def list_scales(session: Session, principal: CurrentPrincipal):
    _require_grade_access(session, principal, manage=False)
    return session.exec(select(GradingScale).where(
        GradingScale.organization_id == principal.organization_id,
        GradingScale.institution_id == principal.institution_id,
    ).order_by(GradingScale.name)).all()


def create_scale(
    session: Session,
    principal: CurrentPrincipal,
    payload: GradingScaleCreate,
):
    _require_grade_access(session, principal, manage=True)
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
    _require_grade_access(session, principal, manage=True)
    scale = _get(session, GradingScale, scale_id, "Grading scale", principal)
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


def list_categories(session: Session, principal: CurrentPrincipal):
    _require_grade_access(session, principal, manage=False)
    return session.exec(select(AssessmentCategory).where(
        AssessmentCategory.organization_id == principal.organization_id,
        AssessmentCategory.institution_id == principal.institution_id,
    ).order_by(AssessmentCategory.created_at)).all()


def create_category(
    session: Session,
    principal: CurrentPrincipal,
    payload: AssessmentCategoryCreate,
):
    _require_grade_access(session, principal, manage=True, course_offering_id=payload.course_offering_id)
    offering = _get(session, CourseOffering, payload.course_offering_id, "Course offering", principal)
    grading_period = _get(session, GradingPeriod, payload.grading_period_id, "Grading period", principal)
    _assert_offering_period(session, principal, offering, grading_period)
    entity = AssessmentCategory(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        section_id=offering.section_id,
        **payload.model_dump(),
    )
    session.add(entity)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action="ASSESSMENT_CATEGORY_CREATED", entity_type="AssessmentCategory", entity_id=entity.id,
                 metadata={"course_offering_id": str(offering.id), "grading_period_id": str(grading_period.id)})
    _assessment_event(session, principal, event_type="assessment.category.created", aggregate_id=entity.id,
                      payload={"course_offering_id": str(offering.id), "grading_period_id": str(grading_period.id), "section_id": str(offering.section_id)})
    session.commit()
    session.refresh(entity)
    return entity


def list_assessments(session: Session, principal: CurrentPrincipal, course_offering_id: UUID | None = None):
    _require_grade_access(session, principal, manage=False, course_offering_id=course_offering_id)
    query = select(Assessment).where(
        Assessment.organization_id == principal.organization_id,
        Assessment.institution_id == principal.institution_id,
    )
    if course_offering_id is not None:
        query = query.where(Assessment.course_offering_id == course_offering_id)
    return session.exec(query.order_by(Assessment.created_at.desc())).all()


def _assert_offering_period(session: Session, principal: CurrentPrincipal, offering: CourseOffering, grading_period: GradingPeriod) -> None:
    academic_period = _get(session, AcademicPeriod, offering.academic_period_id, "Academic period", principal)
    if grading_period.academic_period_id != offering.academic_period_id:
        raise HTTPException(status_code=409, detail="Grading period does not belong to this course period")
    if academic_period.status != "ACTIVE" or grading_period.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Assessment period is not open for academic operations")
    if grading_period.starts_on < academic_period.starts_on or grading_period.ends_on > academic_period.ends_on:
        raise HTTPException(status_code=409, detail="Grading period is outside its academic period")


def create_assessment(
    session: Session,
    principal: CurrentPrincipal,
    payload: AssessmentCreate,
):
    _require_grade_access(session, principal, manage=True, course_offering_id=payload.course_offering_id)
    _operation_lock(session, principal, "assessment-create", payload.operation_id)
    previous_operation = session.exec(
        text("""SELECT entity_id, metadata_json FROM audit_logs
        WHERE institution_id=:institution_id AND entity_type='Assessment'
          AND action='ASSESSMENT_CREATED'
          AND metadata_json->>'operation_id'=:operation_id LIMIT 1"""),
        params={"institution_id": principal.institution_id, "operation_id": str(payload.operation_id)},
    ).first()
    request_fingerprint = {
        "course_offering_id": str(payload.course_offering_id),
        "grading_period_id": str(payload.grading_period_id),
        "assessment_category_id": str(payload.assessment_category_id),
        "code": payload.code,
        "title": payload.title,
        "max_score": format(Decimal(str(payload.max_score)).quantize(Decimal("0.001")), "f"),
        "due_on": payload.due_on.isoformat() if payload.due_on else None,
    }
    request_hash = hashlib.sha256(
        json.dumps(request_fingerprint, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if previous_operation is not None:
        metadata = previous_operation[1]
        if metadata.get("request_fingerprint") != request_hash:
            raise HTTPException(status_code=409, detail="Operation id was already used for another assessment command")
        return _get(session, Assessment, previous_operation[0], "Assessment", principal)

    offering = _get(session, CourseOffering, payload.course_offering_id, "Course offering", principal)
    if offering.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Course offering is not active")
    grading_period = _get(session, GradingPeriod, payload.grading_period_id, "Grading period", principal)
    _assert_offering_period(session, principal, offering, grading_period)
    if payload.due_on is not None and not grading_period.starts_on <= payload.due_on <= grading_period.ends_on:
        raise HTTPException(status_code=409, detail="Assessment date is outside the grading period")
    category = _get(
        session,
        AssessmentCategory,
        payload.assessment_category_id,
        "Assessment category",
        principal,
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
        **payload.model_dump(exclude={"operation_id"}),
    )
    session.add(entity)
    session.flush()
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="ASSESSMENT_CREATED",
        entity_type="Assessment",
        entity_id=entity.id,
        metadata={"operation_id": str(payload.operation_id), "request_fingerprint": request_hash},
    )
    _assessment_event(
        session,
        principal,
        event_type="assessment.created",
        aggregate_id=entity.id,
        payload={
            "course_offering_id": str(offering.id),
            "grading_period_id": str(grading_period.id),
            "section_id": str(offering.section_id),
            "status": "DRAFT",
            "max_score": request_fingerprint["max_score"],
        },
    )
    session.commit()
    session.refresh(entity)
    return entity


def list_entries(session: Session, principal: CurrentPrincipal, assessment_id: UUID):
    if not isinstance(principal, TeacherPrincipal):
        _require_grade_access(session, principal, manage=False)
    assessment = _get(session, Assessment, assessment_id, "Assessment", principal)
    _require_grade_access(session, principal, manage=False, course_offering_id=assessment.course_offering_id)
    entries = session.exec(
        select(GradeEntry)
        .where(
            GradeEntry.assessment_id == assessment_id,
            GradeEntry.organization_id == principal.organization_id,
            GradeEntry.institution_id == principal.institution_id,
        )
        .order_by(GradeEntry.created_at)
    ).all()
    return [GradeEntryRead.model_validate({
        **entry.model_dump(),
        "revision": _grade_revision(session, principal, entry.id),
    }) for entry in entries]


def upsert_entry(
    session: Session,
    principal: CurrentPrincipal,
    assessment_id: UUID,
    payload: GradeEntryUpsert,
):
    assignment_id = payload.student_section_assignment_id
    assessment = _scope_query(session, Assessment, assessment_id, principal, "Assessment", lock=True)
    _require_grade_access(session, principal, manage=True, course_offering_id=assessment.course_offering_id)
    _operation_lock(session, principal, "grade-result", payload.operation_id)
    request_value = {
        "score": format(Decimal(str(payload.score)).quantize(Decimal("0.001")), "f") if payload.score is not None else None,
        "status": payload.status,
        "feedback": payload.feedback,
    }
    request_fingerprint = _grade_request_fingerprint(request_value)
    prior = session.exec(
        text("""SELECT entity_id, metadata_json FROM audit_logs
        WHERE institution_id=:institution_id AND entity_type='GradeEntry'
          AND action IN ('GRADE_RESULT_RECORDED','GRADE_RESULT_CORRECTED','GRADE_RESULT_NOOP')
          AND metadata_json->>'operation_id'=:operation_id LIMIT 1"""),
        params={"institution_id": principal.institution_id, "operation_id": str(payload.operation_id)},
    ).first()
    if prior is not None:
        metadata = prior[1]
        prior_fingerprint = metadata.get("request_fingerprint")
        same_request = (
            prior_fingerprint == request_fingerprint
            if prior_fingerprint is not None
            else metadata.get("new_value") == request_value
        )
        if (
            metadata.get("assessment_id") != str(assessment_id)
            or metadata.get("student_section_assignment_id") != str(assignment_id)
            or not same_request
            or metadata.get("correction_reason") != payload.correction_reason
        ):
            raise HTTPException(status_code=409, detail="Operation id was already used for another result command")
        if assessment.status in {"CLOSED", "ARCHIVED"}:
            raise HTTPException(status_code=409, detail="Assessment is not editable")
        offering = _get(session, CourseOffering, assessment.course_offering_id, "Course offering", principal)
        eligible = session.exec(
            text("""SELECT 1 FROM student_section_assignments ssa
            JOIN enrollments e ON e.id=ssa.enrollment_id
            JOIN student_profiles sp ON sp.id=e.student_profile_id
            WHERE ssa.id=:assignment_id AND ssa.organization_id=:organization_id
              AND ssa.institution_id=:institution_id AND ssa.section_id=:section_id
              AND ssa.academic_period_id=:academic_period_id AND ssa.status='ACTIVE'
              AND ssa.assigned_on<=CURRENT_DATE AND (ssa.ended_on IS NULL OR ssa.ended_on>=CURRENT_DATE)
              AND e.organization_id=:organization_id AND e.institution_id=:institution_id
              AND e.academic_period_id=:academic_period_id AND e.status='ACTIVE'
              AND sp.organization_id=:organization_id AND sp.institution_id=:institution_id AND sp.status='ACTIVE'
            LIMIT 1"""),
            params={
                "assignment_id": assignment_id,
                "organization_id": principal.organization_id,
                "institution_id": principal.institution_id,
                "section_id": assessment.section_id,
                "academic_period_id": offering.academic_period_id,
            },
        ).first()
        if eligible is None:
            raise HTTPException(status_code=404, detail="Student is not eligible for this assessment")
        entry = _scope_query(session, GradeEntry, prior[0], principal, "Grade entry")
        return GradeEntryRead.model_validate({**entry.model_dump(), "revision": _grade_revision(session, principal, entry.id)})

    if assessment.status in {"CLOSED", "ARCHIVED"}:
        raise HTTPException(status_code=409, detail="Assessment is not editable")
    grading_period = _get(session, GradingPeriod, assessment.grading_period_id, "Grading period", principal)
    offering = _get(session, CourseOffering, assessment.course_offering_id, "Course offering", principal)
    academic_period = _get(session, AcademicPeriod, offering.academic_period_id, "Academic period", principal)
    if grading_period.academic_period_id != offering.academic_period_id:
        raise HTTPException(status_code=409, detail="Assessment period does not match its course")
    if grading_period.status != "ACTIVE" or academic_period.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Academic period is not open for result changes")
    if payload.status not in _VALID_RESULTS:
        raise HTTPException(status_code=422, detail="Unsupported result status")
    if (payload.status == "GRADED") != (payload.score is not None):
        raise HTTPException(status_code=422, detail="Only GRADED results may carry a numeric score")
    score = Decimal(str(payload.score)) if payload.score is not None else None
    if score is not None and score > Decimal(str(assessment.max_score)):
        raise HTTPException(status_code=422, detail="Score cannot exceed assessment max_score")

    eligibility = session.exec(
        text("""SELECT e.student_profile_id
        FROM student_section_assignments ssa
        JOIN enrollments e ON e.id=ssa.enrollment_id
        JOIN student_profiles sp ON sp.id=e.student_profile_id
        WHERE ssa.id=:assignment_id AND ssa.organization_id=:organization_id
          AND ssa.institution_id=:institution_id AND ssa.section_id=:section_id
          AND ssa.academic_period_id=:academic_period_id AND ssa.status='ACTIVE'
          AND ssa.assigned_on<=CURRENT_DATE AND (ssa.ended_on IS NULL OR ssa.ended_on>=CURRENT_DATE)
          AND e.organization_id=:organization_id AND e.institution_id=:institution_id AND e.status='ACTIVE'
          AND e.academic_period_id=:academic_period_id
          AND sp.organization_id=:organization_id AND sp.institution_id=:institution_id AND sp.status='ACTIVE'
        LIMIT 1"""),
        params={
            "assignment_id": assignment_id,
            "organization_id": principal.organization_id,
            "institution_id": principal.institution_id,
            "section_id": assessment.section_id,
            "academic_period_id": offering.academic_period_id,
        },
    ).first()
    if eligibility is None:
        raise HTTPException(status_code=404, detail="Student is not eligible for this assessment")

    existing = session.exec(
        select(GradeEntry).where(
            GradeEntry.assessment_id == assessment_id,
            GradeEntry.student_section_assignment_id == assignment_id,
            GradeEntry.organization_id == principal.organization_id,
            GradeEntry.institution_id == principal.institution_id,
        ).with_for_update()
    ).first()
    current_revision = _grade_revision(session, principal, existing.id) if existing else 0
    if payload.expected_revision != current_revision:
        raise HTTPException(status_code=409, detail="Result changed; refresh before submitting")
    if existing is not None and payload.correction_reason is None:
        raise HTTPException(status_code=422, detail="A bounded correction reason is required")
    previous_value = _grade_value(existing)
    if _grade_command_value(existing) == request_value:
        record_audit(
            session,
            institution_id=principal.institution_id,
            actor_user_id=principal.user_id,
            action="GRADE_RESULT_NOOP",
            entity_type="GradeEntry",
            entity_id=existing.id,
            metadata={
                "operation_id": str(payload.operation_id),
                "assessment_id": str(assessment_id),
                "student_section_assignment_id": str(assignment_id),
                "new_value": _grade_value(existing),
                "request_fingerprint": request_fingerprint,
                "correction_reason": payload.correction_reason,
            },
        )
        session.commit()
        return GradeEntryRead.model_validate({**existing.model_dump(), "revision": current_revision})

    revision = current_revision + 1
    event_type = "student.grade.updated" if existing is not None else "student.grade.recorded"
    if existing is None:
        entry = GradeEntry(
            organization_id=principal.organization_id,
            institution_id=principal.institution_id,
            section_id=assessment.section_id,
            assessment_id=assessment_id,
            student_section_assignment_id=assignment_id,
            score=payload.score,
            status=payload.status,
            feedback=payload.feedback,
        )
        session.add(entry)
        session.flush()
    else:
        entry = existing
        entry.score = payload.score
        entry.status = payload.status
        entry.feedback = payload.feedback
        entry.updated_at = datetime.now(UTC)
        session.add(entry)
        session.flush()

    metadata = {
        "operation_id": str(payload.operation_id),
        "result_revision": revision,
        "assessment_id": str(assessment_id),
        "student_section_assignment_id": str(assignment_id),
        "previous_value": previous_value,
        "new_value": _grade_value(entry),
        "request_fingerprint": request_fingerprint,
        "correction_reason": payload.correction_reason,
    }
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="GRADE_RESULT_CORRECTED" if existing is not None else "GRADE_RESULT_RECORDED",
        entity_type="GradeEntry",
        entity_id=entry.id,
        metadata=metadata,
    )
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type="grade_entry",
        aggregate_id=entry.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(eligibility[0]),
            "student_section_assignment_id": str(assignment_id),
            "assessment_id": str(assessment.id),
            "section_id": str(assessment.section_id),
            "previous_status": previous_value["status"] if previous_value else None,
            "previous_score": previous_value["score"] if previous_value else None,
            "status": entry.status,
            "score": float(score) if score is not None else None,
            "result_revision": revision,
        },
    )
    session.commit()
    session.refresh(entry)
    return GradeEntryRead.model_validate({**entry.model_dump(), "revision": revision})


def change_assessment_status(
    session: Session,
    principal: CurrentPrincipal,
    assessment_id: UUID,
    payload: AssessmentStatusChange,
) -> Assessment:
    assessment = _scope_query(session, Assessment, assessment_id, principal, "Assessment", lock=True)
    _require_grade_access(session, principal, manage=True, course_offering_id=assessment.course_offering_id)
    _operation_lock(session, principal, "assessment-status", payload.operation_id)
    prior = session.exec(
        text("""SELECT entity_id, metadata_json FROM audit_logs
        WHERE institution_id=:institution_id AND entity_type='Assessment'
          AND action='ASSESSMENT_STATUS_CHANGED'
          AND metadata_json->>'operation_id'=:operation_id LIMIT 1"""),
        params={"institution_id": principal.institution_id, "operation_id": str(payload.operation_id)},
    ).first()
    if prior is not None:
        metadata = prior[1]
        if metadata.get("assessment_id") != str(assessment_id) or metadata.get("status") != payload.status:
            raise HTTPException(status_code=409, detail="Operation id was already used for another assessment transition")
        return assessment

    if assessment.status != payload.expected_status:
        raise HTTPException(status_code=409, detail="Assessment status changed; refresh before submitting")
    if payload.status == payload.expected_status:
        return assessment
    allowed = {
        "DRAFT": {"PUBLISHED", "ARCHIVED"},
        "PUBLISHED": {"CLOSED"},
        "CLOSED": {"ARCHIVED"},
        "ARCHIVED": set(),
    }
    if payload.status not in allowed[assessment.status]:
        raise HTTPException(status_code=409, detail="Invalid assessment status transition")
    if assessment.status == "DRAFT" and payload.status == "ARCHIVED":
        used = session.exec(select(GradeEntry.id).where(GradeEntry.assessment_id == assessment.id).limit(1)).first()
        if used is not None:
            raise HTTPException(status_code=409, detail="An assessment with results cannot be archived from DRAFT")
    previous_status = assessment.status
    assessment.status = payload.status
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="ASSESSMENT_STATUS_CHANGED",
        entity_type="Assessment",
        entity_id=assessment.id,
        metadata={"operation_id": str(payload.operation_id), "assessment_id": str(assessment.id), "previous_status": previous_status, "status": payload.status},
    )
    _assessment_event(
        session,
        principal,
        event_type="assessment.status_changed",
        aggregate_id=assessment.id,
        payload={"course_offering_id": str(assessment.course_offering_id), "section_id": str(assessment.section_id), "previous_status": previous_status, "status": payload.status},
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def grade_entry_history(
    session: Session,
    principal: CurrentPrincipal,
    assessment_id: UUID,
    assignment_id: UUID,
) -> list[GradeEntryHistoryRead]:
    if not isinstance(principal, TeacherPrincipal):
        _require_grade_access(session, principal, manage=False)
    assessment = _scope_query(session, Assessment, assessment_id, principal, "Assessment")
    _require_grade_access(session, principal, manage=False, course_offering_id=assessment.course_offering_id)
    entry = session.exec(select(GradeEntry).where(
        GradeEntry.assessment_id == assessment_id,
        GradeEntry.student_section_assignment_id == assignment_id,
        GradeEntry.organization_id == principal.organization_id,
        GradeEntry.institution_id == principal.institution_id,
    )).first()
    if entry is None:
        return []
    rows = session.exec(select(AuditLog).where(
        AuditLog.institution_id == principal.institution_id,
        AuditLog.entity_type == "GradeEntry",
        AuditLog.entity_id == entry.id,
        AuditLog.action.in_(_GRADE_OPERATION_ACTIONS),
    ).order_by(AuditLog.created_at, AuditLog.id)).all()
    return [GradeEntryHistoryRead(
        revision=int(row.metadata_json["result_revision"]),
        actor_user_id=row.actor_user_id,
        created_at=row.created_at,
        correction_reason=row.metadata_json.get("correction_reason"),
        previous_value=row.metadata_json.get("previous_value"),
        new_value=row.metadata_json["new_value"],
    ) for row in rows if "result_revision" in row.metadata_json]
