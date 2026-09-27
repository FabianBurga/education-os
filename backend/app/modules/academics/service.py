from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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
    StudentSectionAssignmentTransfer,
    SubjectCreate,
    TeachingAssignmentCreate,
    TeachingAssignmentEnd,
)
from app.modules.audit.service import record_audit
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.events.service import enqueue_canonical_event
from app.modules.families.models import StaffProfile
from app.modules.students.models import StudentProfile
from app.modules.tenancy.models import Campus, Institution


def require_academic_permission(session: Session, principal: CurrentPrincipal, key: str) -> None:
    if key not in {"academics.read", "academics.manage", "academics.assign", "students.read", "enrollments.read"}:
        raise ValueError("Unsupported academic permission")
    permitted = session.exec(
        text("""SELECT 1
            FROM memberships m
            JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN roles r ON r.id=mr.role_id AND r.institution_id=m.institution_id
            JOIN role_permissions rp ON rp.role_id=mr.role_id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id=:user_id AND m.institution_id=:institution_id AND m.status='ACTIVE'
              AND p.key=:permission LIMIT 1"""),
        params={
            "user_id": principal.user_id,
            "institution_id": principal.institution_id,
            "permission": key,
        },
    ).first()
    if permitted is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Academic structure permission required")


def list_academic_options(session: Session, principal: CurrentPrincipal) -> dict[str, list]:
    require_academic_permission(session, principal, "academics.read")
    periods = session.exec(select(AcademicPeriod).where(
        AcademicPeriod.organization_id == principal.organization_id,
        AcademicPeriod.institution_id == principal.institution_id,
        AcademicPeriod.status != "CLOSED",
    ).order_by(AcademicPeriod.starts_on.desc(), AcademicPeriod.id)).all()
    campuses = session.exec(select(Campus).join(
        Institution, Institution.id == Campus.institution_id,
    ).where(
        Campus.institution_id == principal.institution_id,
        Institution.organization_id == principal.organization_id,
    ).order_by(Campus.name, Campus.id)).all()
    return {"periods": periods, "campuses": campuses}


def list_assignment_options(session: Session, principal: CurrentPrincipal) -> list[dict[str, str]]:
    require_academic_permission(session, principal, "academics.assign")
    staff = session.exec(select(StaffProfile).where(
        StaffProfile.organization_id == principal.organization_id,
        StaffProfile.institution_id == principal.institution_id,
        StaffProfile.status == "ACTIVE",
    ).order_by(StaffProfile.staff_code, StaffProfile.id)).all()
    return [{"id": str(item.id), "label": item.staff_code or f"Personal · {str(item.id)[:8]}"} for item in staff]


def _scoped(session: Session, model, entity_id: UUID, principal: CurrentPrincipal, label: str):
    entity = session.exec(select(model).where(
        model.id == entity_id,
        model.organization_id == principal.organization_id,
        model.institution_id == principal.institution_id,
    )).first()
    if entity is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return entity


def _active_period(session: Session, principal: CurrentPrincipal, period_id: UUID) -> AcademicPeriod:
    period = _scoped(session, AcademicPeriod, period_id, principal, "Academic period")
    if period.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Academic period is closed")
    return period


def _campus(session: Session, principal: CurrentPrincipal, campus_id: UUID):
    campus = session.exec(text("""SELECT c.id FROM campuses c
        JOIN institutions i ON i.id=c.institution_id
        WHERE c.id=:campus_id AND c.institution_id=:institution_id
          AND i.organization_id=:organization_id"""), params={
        "campus_id": campus_id,
        "institution_id": principal.institution_id,
        "organization_id": principal.organization_id,
    }).first()
    if campus is None:
        raise HTTPException(status_code=404, detail="Campus not found")
    return campus


def _evidence(
    session: Session,
    principal: CurrentPrincipal,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    action: str,
    metadata: dict | None = None,
    payload: dict | None = None,
) -> None:
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type=event_type,
        event_version=1,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_user_id=principal.user_id,
        payload=payload or {"entity_id": str(aggregate_id)},
        metadata=metadata or {},
    )
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action=action,
        entity_type=aggregate_type,
        entity_id=aggregate_id,
        metadata=metadata or {},
    )


def _commit(session: Session, entity):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Academic structure conflicts with existing records") from exc
    session.refresh(entity)
    return entity


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Academic structure conflicts with existing records") from exc


def list_levels(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(AcademicLevel).where(
        AcademicLevel.organization_id == principal.organization_id,
        AcademicLevel.institution_id == principal.institution_id,
    ).order_by(AcademicLevel.sort_order, AcademicLevel.name, AcademicLevel.id)).all()


def create_level(session: Session, principal: CurrentPrincipal, payload: AcademicLevelCreate):
    require_academic_permission(session, principal, "academics.manage")
    entity = AcademicLevel(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="academic.level.created", aggregate_type="academic_level", aggregate_id=entity.id, action="ACADEMIC_LEVEL_CREATED", metadata={"code": entity.code})
    return _commit(session, entity)


def list_grades(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(GradeLevel).where(
        GradeLevel.organization_id == principal.organization_id,
        GradeLevel.institution_id == principal.institution_id,
    ).order_by(GradeLevel.sort_order, GradeLevel.name, GradeLevel.id)).all()


def create_grade(session: Session, principal: CurrentPrincipal, payload: GradeLevelCreate):
    require_academic_permission(session, principal, "academics.manage")
    _scoped(session, AcademicLevel, payload.academic_level_id, principal, "Academic level")
    entity = GradeLevel(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="academic.grade.created", aggregate_type="grade_level", aggregate_id=entity.id, action="ACADEMIC_GRADE_CREATED", metadata={"code": entity.code})
    return _commit(session, entity)


def list_subjects(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(Subject).where(
        Subject.organization_id == principal.organization_id,
        Subject.institution_id == principal.institution_id,
    ).order_by(Subject.name, Subject.id)).all()


def create_subject(session: Session, principal: CurrentPrincipal, payload: SubjectCreate):
    require_academic_permission(session, principal, "academics.manage")
    entity = Subject(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="academic.subject.created", aggregate_type="subject", aggregate_id=entity.id, action="ACADEMIC_SUBJECT_CREATED", metadata={"code": entity.code})
    return _commit(session, entity)


def list_sections(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(Section).where(
        Section.organization_id == principal.organization_id,
        Section.institution_id == principal.institution_id,
    ).order_by(Section.name, Section.id)).all()


def create_section(session: Session, principal: CurrentPrincipal, payload: SectionCreate):
    require_academic_permission(session, principal, "academics.manage")
    period = _active_period(session, principal, payload.academic_period_id)
    _campus(session, principal, payload.campus_id)
    _scoped(session, GradeLevel, payload.grade_level_id, principal, "Grade level")
    entity = Section(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="academic.section.created", aggregate_type="section", aggregate_id=entity.id, action="ACADEMIC_SECTION_CREATED", metadata={"academic_period_id": str(period.id), "code": entity.code})
    return _commit(session, entity)


def list_curriculum_plans(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(CurriculumPlan).where(
        CurriculumPlan.organization_id == principal.organization_id,
        CurriculumPlan.institution_id == principal.institution_id,
    ).order_by(CurriculumPlan.name, CurriculumPlan.id)).all()


def create_curriculum_plan(session: Session, principal: CurrentPrincipal, payload: CurriculumPlanCreate):
    require_academic_permission(session, principal, "academics.manage")
    _active_period(session, principal, payload.academic_period_id)
    _scoped(session, GradeLevel, payload.grade_level_id, principal, "Grade level")
    entity = CurriculumPlan(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="curriculum.plan.created", aggregate_type="curriculum_plan", aggregate_id=entity.id, action="CURRICULUM_PLAN_CREATED", metadata={"code": entity.code})
    return _commit(session, entity)


def list_curriculum_subjects(session: Session, principal: CurrentPrincipal, plan_id: UUID):
    require_academic_permission(session, principal, "academics.read")
    _scoped(session, CurriculumPlan, plan_id, principal, "Curriculum plan")
    return session.exec(select(CurriculumSubject).where(
        CurriculumSubject.organization_id == principal.organization_id,
        CurriculumSubject.institution_id == principal.institution_id,
        CurriculumSubject.curriculum_plan_id == plan_id,
    ).order_by(CurriculumSubject.sort_order, CurriculumSubject.id)).all()


def add_curriculum_subject(session: Session, principal: CurrentPrincipal, plan_id: UUID, payload: CurriculumSubjectCreate):
    require_academic_permission(session, principal, "academics.manage")
    plan = _scoped(session, CurriculumPlan, plan_id, principal, "Curriculum plan")
    _active_period(session, principal, plan.academic_period_id)
    _scoped(session, Subject, payload.subject_id, principal, "Subject")
    entity = CurriculumSubject(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        curriculum_plan_id=plan_id, **payload.model_dump(),
    )
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="curriculum.subject.added", aggregate_type="curriculum_subject", aggregate_id=entity.id, action="CURRICULUM_SUBJECT_ADDED", metadata={"curriculum_plan_id": str(plan_id), "subject_id": str(entity.subject_id)})
    return _commit(session, entity)


def list_course_offerings(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(CourseOffering).where(
        CourseOffering.organization_id == principal.organization_id,
        CourseOffering.institution_id == principal.institution_id,
    ).order_by(CourseOffering.created_at, CourseOffering.id)).all()


def create_course_offering(session: Session, principal: CurrentPrincipal, payload: CourseOfferingCreate):
    require_academic_permission(session, principal, "academics.manage")
    section = _scoped(session, Section, payload.section_id, principal, "Section")
    period = _active_period(session, principal, section.academic_period_id)
    _scoped(session, Subject, payload.subject_id, principal, "Subject")
    if payload.curriculum_subject_id:
        relationship = _scoped(session, CurriculumSubject, payload.curriculum_subject_id, principal, "Curriculum subject")
        plan = _scoped(session, CurriculumPlan, relationship.curriculum_plan_id, principal, "Curriculum plan")
        if relationship.subject_id != payload.subject_id or plan.academic_period_id != period.id or plan.grade_level_id != section.grade_level_id:
            raise HTTPException(status_code=409, detail="Curriculum subject does not match section, subject, and period")
    entity = CourseOffering(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        academic_period_id=period.id, **payload.model_dump(),
    )
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="course.offering.created", aggregate_type="course_offering", aggregate_id=entity.id, action="COURSE_OFFERING_CREATED", metadata={"section_id": str(section.id), "subject_id": str(entity.subject_id)})
    return _commit(session, entity)


def list_teaching_assignments(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(TeachingAssignment).where(
        TeachingAssignment.organization_id == principal.organization_id,
        TeachingAssignment.institution_id == principal.institution_id,
    ).order_by(TeachingAssignment.starts_on, TeachingAssignment.id)).all()


def create_teaching_assignment(session: Session, principal: CurrentPrincipal, payload: TeachingAssignmentCreate):
    require_academic_permission(session, principal, "academics.assign")
    offering = _scoped(session, CourseOffering, payload.course_offering_id, principal, "Course offering")
    period = _active_period(session, principal, offering.academic_period_id)
    staff = session.exec(select(StaffProfile).where(
        StaffProfile.id == payload.staff_profile_id,
        StaffProfile.organization_id == principal.organization_id,
        StaffProfile.institution_id == principal.institution_id,
        StaffProfile.status == "ACTIVE",
    )).first()
    if staff is None:
        raise HTTPException(status_code=404, detail="Active staff profile not found")
    for day in (payload.starts_on, payload.ends_on):
        if day is not None and not period.starts_on <= day <= period.ends_on:
            raise HTTPException(status_code=422, detail="Assignment dates must fall within the academic period")
    entity = TeachingAssignment(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="teaching.assignment.created", aggregate_type="teaching_assignment", aggregate_id=entity.id, action="TEACHING_ASSIGNMENT_CREATED", metadata={"course_offering_id": str(offering.id), "staff_profile_id": str(staff.id)})
    return _commit(session, entity)


def end_teaching_assignment(
    session: Session,
    principal: CurrentPrincipal,
    assignment_id: UUID,
    payload: TeachingAssignmentEnd,
) -> TeachingAssignment:
    require_academic_permission(session, principal, "academics.assign")
    assignment = session.exec(select(TeachingAssignment).where(
        TeachingAssignment.id == assignment_id,
        TeachingAssignment.organization_id == principal.organization_id,
        TeachingAssignment.institution_id == principal.institution_id,
    ).with_for_update()).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Teaching assignment not found")
    if assignment.ends_on == payload.ends_on:
        return assignment
    if assignment.ends_on != payload.expected_ends_on:
        raise HTTPException(status_code=409, detail="Teaching assignment changed; refresh before ending it")
    offering = _scoped(session, CourseOffering, assignment.course_offering_id, principal, "Course offering")
    period = _active_period(session, principal, offering.academic_period_id)
    if (assignment.starts_on and payload.ends_on < assignment.starts_on) or not period.starts_on <= payload.ends_on <= period.ends_on:
        raise HTTPException(status_code=422, detail="End date must fall within the teaching assignment period")
    previous_end = assignment.ends_on
    assignment.ends_on = payload.ends_on
    session.add(assignment)
    _flush(session)
    _evidence(
        session, principal,
        event_type="teaching.assignment.updated",
        aggregate_type="teaching_assignment",
        aggregate_id=assignment.id,
        action="TEACHING_ASSIGNMENT_ENDED",
        metadata={"previous_ends_on": previous_end.isoformat() if previous_end else None,
                  "ends_on": payload.ends_on.isoformat()},
        payload={"teaching_assignment_id": str(assignment.id),
                 "course_offering_id": str(assignment.course_offering_id),
                 "staff_profile_id": str(assignment.staff_profile_id),
                 "previous_ends_on": previous_end.isoformat() if previous_end else None,
                 "ends_on": payload.ends_on.isoformat()},
    )
    return _commit(session, assignment)


def create_student_section_assignment(session: Session, principal: CurrentPrincipal, payload: StudentSectionAssignmentCreate):
    require_academic_permission(session, principal, "academics.assign")
    enrollment = session.exec(select(Enrollment).where(
        Enrollment.id == payload.enrollment_id,
        Enrollment.organization_id == principal.organization_id,
        Enrollment.institution_id == principal.institution_id,
    ).with_for_update()).first()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    section = _scoped(session, Section, payload.section_id, principal, "Section")
    period = _active_period(session, principal, enrollment.academic_period_id)
    _validate_placement_target(session, principal, enrollment, section, period, payload.assigned_on)
    current = _current_placement(session, enrollment.id)
    if current is not None:
        if current.section_id == section.id and current.assigned_on == payload.assigned_on:
            return current
        raise HTTPException(status_code=409, detail="Enrollment already has a current placement")
    entity = StudentSectionAssignment(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        academic_period_id=section.academic_period_id, **payload.model_dump(),
    )
    session.add(entity)
    _flush(session)
    _evidence(
        session,
        principal,
        event_type="student.section.assigned",
        aggregate_type="student_section_assignment",
        aggregate_id=entity.id,
        action="STUDENT_SECTION_ASSIGNED",
        metadata={"section_id": str(section.id)},
        payload={
            "student_section_assignment_id": str(entity.id),
            "student_profile_id": str(enrollment.student_profile_id),
            "enrollment_id": str(enrollment.id),
            "academic_period_id": str(section.academic_period_id),
            "section_id": str(section.id),
            "assigned_on": entity.assigned_on.isoformat(),
        },
    )
    return _commit(session, entity)


def _current_placement(session: Session, enrollment_id: UUID) -> StudentSectionAssignment | None:
    return session.exec(select(StudentSectionAssignment).where(
        StudentSectionAssignment.enrollment_id == enrollment_id,
        StudentSectionAssignment.status == "ACTIVE",
    ).with_for_update()).first()


def _validate_placement_target(
    session: Session,
    principal: CurrentPrincipal,
    enrollment: Enrollment,
    section: Section,
    period: AcademicPeriod,
    effective_on: date,
) -> None:
    student = session.exec(select(StudentProfile).where(
        StudentProfile.id == enrollment.student_profile_id,
        StudentProfile.organization_id == principal.organization_id,
        StudentProfile.institution_id == principal.institution_id,
    )).first()
    if student is None or student.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="An active student profile is required for placement")
    if enrollment.status != "ACTIVE" or enrollment.enrolled_on is None:
        raise HTTPException(status_code=409, detail="An active enrollment is required for placement")
    if section.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Target section is not active")
    if section.academic_period_id != enrollment.academic_period_id:
        raise HTTPException(status_code=409, detail="Enrollment and section belong to different academic periods")
    if section.campus_id != enrollment.campus_id:
        raise HTTPException(status_code=409, detail="Placement cannot move across campuses")
    if period.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Academic period must be active for placement")
    if not period.starts_on <= effective_on <= period.ends_on or effective_on < enrollment.enrolled_on:
        raise HTTPException(status_code=422, detail="Placement date must fall within the active enrollment period")


def transfer_student_section_assignment(
    session: Session,
    principal: CurrentPrincipal,
    enrollment_id: UUID,
    payload: StudentSectionAssignmentTransfer,
) -> StudentSectionAssignment:
    require_academic_permission(session, principal, "academics.assign")
    enrollment = session.exec(select(Enrollment).where(
        Enrollment.id == enrollment_id,
        Enrollment.organization_id == principal.organization_id,
        Enrollment.institution_id == principal.institution_id,
    ).with_for_update()).first()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    current = _current_placement(session, enrollment.id)
    target = _scoped(session, Section, payload.section_id, principal, "Section")
    period = _active_period(session, principal, enrollment.academic_period_id)
    _validate_placement_target(session, principal, enrollment, target, period, payload.effective_on)
    if current is not None and current.section_id == target.id and current.assigned_on == payload.effective_on:
        return current
    if current is None or current.id != payload.expected_current_placement_id:
        raise HTTPException(status_code=409, detail="Current placement changed; refresh before transferring")
    if target.id == current.section_id:
        raise HTTPException(status_code=409, detail="Target section is already the current placement")
    if payload.effective_on <= current.assigned_on:
        raise HTTPException(status_code=422, detail="Transfer date must be after the current placement start")
    if target.campus_id != _scoped(session, Section, current.section_id, principal, "Current section").campus_id:
        raise HTTPException(status_code=409, detail="Cross-campus placement transfer is not supported")

    later_attendance = session.exec(text("""SELECT 1
        FROM attendance_records ar JOIN class_sessions cs ON cs.id=ar.class_session_id
        WHERE ar.student_section_assignment_id=:placement AND cs.session_date >= :effective_on
        LIMIT 1"""), params={"placement": current.id, "effective_on": payload.effective_on}).first()
    later_grade = session.exec(text("""SELECT 1
        FROM grade_entries ge JOIN assessments a ON a.id=ge.assessment_id
        WHERE ge.student_section_assignment_id=:placement
          AND (a.due_on >= :effective_on OR a.due_on IS NULL)
        LIMIT 1"""), params={"placement": current.id, "effective_on": payload.effective_on}).first()
    if later_attendance or later_grade:
        raise HTTPException(status_code=409, detail="Transfer would place recorded academic evidence outside its placement dates")

    current.status = "TRANSFERRED"
    current.ended_on = payload.effective_on - timedelta(days=1)
    session.add(current)
    replacement = StudentSectionAssignment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        academic_period_id=enrollment.academic_period_id,
        enrollment_id=enrollment.id,
        section_id=target.id,
        status="ACTIVE",
        assigned_on=payload.effective_on,
    )
    session.add(replacement)
    _flush(session)
    _evidence(
        session, principal,
        event_type="student.section.transferred",
        aggregate_type="student_section_assignment",
        aggregate_id=replacement.id,
        action="STUDENT_SECTION_TRANSFERRED",
        metadata={"from_placement_id": str(current.id), "to_placement_id": str(replacement.id)},
        payload={
            "previous_placement_id": str(current.id),
            "student_section_assignment_id": str(replacement.id),
            "enrollment_id": str(enrollment.id),
            "academic_period_id": str(enrollment.academic_period_id),
            "previous_section_id": str(current.section_id),
            "section_id": str(target.id),
            "effective_on": payload.effective_on.isoformat(),
        },
    )
    return _commit(session, replacement)


def list_student_placements(session: Session, principal: CurrentPrincipal, student_profile_id: UUID):
    require_academic_permission(session, principal, "academics.read")
    require_academic_permission(session, principal, "students.read")
    require_academic_permission(session, principal, "enrollments.read")
    student = session.exec(text("""SELECT id FROM student_profiles
        WHERE id=:student AND organization_id=:organization AND institution_id=:institution"""),
        params={"student": student_profile_id, "organization": principal.organization_id,
                "institution": principal.institution_id}).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    rows = session.exec(text("""SELECT ssa.id, ssa.organization_id, ssa.institution_id,
        ssa.academic_period_id, ssa.enrollment_id, ssa.section_id,
        ssa.status, ssa.assigned_on, ssa.ended_on,
        sec.code AS section_code, sec.name AS section_name,
        e.student_profile_id,
        (ssa.status IN ('ACTIVE','TRANSFERRED') AND ssa.assigned_on <= CURRENT_DATE
          AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)) AS is_current
        FROM student_section_assignments ssa
        JOIN enrollments e ON e.id=ssa.enrollment_id
        JOIN sections sec ON sec.id=ssa.section_id
        WHERE e.student_profile_id=:student AND e.organization_id=:organization
          AND e.institution_id=:institution
          AND sec.organization_id=:organization AND sec.institution_id=:institution
          AND ssa.organization_id=:organization
          AND ssa.institution_id=:institution
        ORDER BY ssa.assigned_on, ssa.created_at, ssa.id"""), params={
        "student": student_profile_id, "organization": principal.organization_id,
        "institution": principal.institution_id,
    }).all()
    return [dict(row._mapping) for row in rows]


def get_placement_options(session: Session, principal: CurrentPrincipal, enrollment_id: UUID):
    require_academic_permission(session, principal, "academics.assign")
    require_academic_permission(session, principal, "enrollments.read")
    enrollment = _scoped(session, Enrollment, enrollment_id, principal, "Enrollment")
    if enrollment.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="An active enrollment is required for placement")
    _active_period(session, principal, enrollment.academic_period_id)
    current = session.exec(select(StudentSectionAssignment).where(
        StudentSectionAssignment.enrollment_id == enrollment.id,
        StudentSectionAssignment.status == "ACTIVE",
    )).first()
    sections = session.exec(text("""SELECT id, code, name FROM sections
        WHERE organization_id=:organization AND institution_id=:institution
          AND academic_period_id=:period AND campus_id=:campus AND status='ACTIVE'
          AND (:current_section IS NULL OR id <> :current_section)
        ORDER BY name, code, id"""), params={
        "organization": principal.organization_id, "institution": principal.institution_id,
        "period": enrollment.academic_period_id, "campus": enrollment.campus_id,
        "current_section": current.section_id if current else None,
    }).all()
    return {
        "sections": [dict(row._mapping) for row in sections],
        "current_placement_id": current.id if current else None,
        "current_section_id": current.section_id if current else None,
    }


def list_section_roster(session: Session, principal: CurrentPrincipal, section_id: UUID, limit: int, offset: int):
    require_academic_permission(session, principal, "academics.read")
    require_academic_permission(session, principal, "students.read")
    if _scoped(session, Section, section_id, principal, "Section") is None:
        raise HTTPException(status_code=404, detail="Section not found")
    rows = session.exec(text("""SELECT ssa.id AS student_section_assignment_id,
        sp.id AS student_profile_id, sp.student_code,
        trim(concat_ws(' ', p.given_names, p.family_names)) AS student_name,
        e.enrollment_number,
        ssa.status AS placement_status, ssa.assigned_on, ssa.ended_on
        FROM student_section_assignments ssa
        JOIN enrollments e ON e.id=ssa.enrollment_id
        JOIN student_profiles sp ON sp.id=e.student_profile_id
        JOIN persons p ON p.id=sp.person_id
        JOIN sections sec ON sec.id=ssa.section_id AND sec.academic_period_id=ssa.academic_period_id
        JOIN academic_periods ap ON ap.id=ssa.academic_period_id
        WHERE ssa.section_id=:section AND ssa.organization_id=:organization
          AND ssa.institution_id=:institution AND ssa.status='ACTIVE'
          AND e.status='ACTIVE' AND e.campus_id=sec.campus_id
          AND e.organization_id=:organization AND e.institution_id=:institution
          AND sp.organization_id=:organization AND sp.institution_id=:institution
          AND sec.organization_id=:organization AND sec.institution_id=:institution
          AND sp.status='ACTIVE' AND sec.status='ACTIVE' AND ap.status='ACTIVE'
          AND ssa.status IN ('ACTIVE','TRANSFERRED') AND ssa.assigned_on <= CURRENT_DATE
          AND (ssa.ended_on IS NULL OR ssa.ended_on >= CURRENT_DATE)
        ORDER BY p.family_names, p.given_names, sp.id
        LIMIT :limit OFFSET :offset"""), params={
        "section": section_id, "organization": principal.organization_id,
        "institution": principal.institution_id, "limit": limit, "offset": offset,
    }).all()
    return [dict(row._mapping) for row in rows]


def list_student_section_assignments(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(StudentSectionAssignment).where(
        StudentSectionAssignment.organization_id == principal.organization_id,
        StudentSectionAssignment.institution_id == principal.institution_id,
    ).order_by(StudentSectionAssignment.created_at, StudentSectionAssignment.id)).all()


def create_schedule_slot(session: Session, principal: CurrentPrincipal, payload: ScheduleSlotCreate):
    require_academic_permission(session, principal, "academics.manage")
    offering = _scoped(session, CourseOffering, payload.course_offering_id, principal, "Course offering")
    _active_period(session, principal, offering.academic_period_id)
    entity = ScheduleSlot(organization_id=principal.organization_id, institution_id=principal.institution_id, **payload.model_dump())
    session.add(entity)
    _flush(session)
    _evidence(session, principal, event_type="schedule.slot.created", aggregate_type="schedule_slot", aggregate_id=entity.id, action="SCHEDULE_SLOT_CREATED", metadata={"course_offering_id": str(offering.id)})
    return _commit(session, entity)


def list_schedule_slots(session: Session, principal: CurrentPrincipal):
    require_academic_permission(session, principal, "academics.read")
    return session.exec(select(ScheduleSlot).where(
        ScheduleSlot.organization_id == principal.organization_id,
        ScheduleSlot.institution_id == principal.institution_id,
    ).order_by(ScheduleSlot.weekday, ScheduleSlot.starts_at, ScheduleSlot.id)).all()
