from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.audit.models import AuditLog
from app.modules.audit.service import record_audit
from app.modules.enrollment.models import AcademicPeriod, Enrollment
from app.modules.events.service import enqueue_canonical_event
from app.modules.students.models import StudentProfile


def require_academic_period_permission(session: Session, principal: CurrentPrincipal, key: str) -> None:
    if key not in {"academics.read", "academics.manage"}:
        raise ValueError("Unsupported academic-period permission")
    row = session.exec(
        text("""SELECT 1 FROM memberships m
        JOIN membership_roles mr ON mr.membership_id=m.id
        JOIN roles r ON r.id=mr.role_id AND r.institution_id=m.institution_id
        JOIN role_permissions rp ON rp.role_id=mr.role_id
        JOIN permissions p ON p.id=rp.permission_id
        WHERE m.user_id=:user_id AND m.institution_id=:institution_id AND m.status='ACTIVE'
          AND p.key=:permission LIMIT 1"""),
        params={"user_id": principal.user_id, "institution_id": principal.institution_id, "permission": key},
    ).first()
    if row is None:
        raise HTTPException(status_code=403, detail="Academic structure permission required")


def create_academic_period(
    session: Session,
    principal: CurrentPrincipal,
    *,
    code: str,
    name: str,
    starts_on: date,
    ends_on: date,
) -> AcademicPeriod:
    require_academic_period_permission(session, principal, "academics.manage")
    if ends_on < starts_on:
        raise HTTPException(status_code=422, detail="Academic period end must not precede its start")
    period = AcademicPeriod(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        code=code,
        name=name,
        starts_on=starts_on,
        ends_on=ends_on,
        status="PLANNED",
    )
    session.add(period)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Academic period code already exists") from exc
    enqueue_canonical_event(
        session, institution_id=principal.institution_id,
        event_type="academic_period.created", event_version=1,
        aggregate_type="academic_period", aggregate_id=period.id,
        actor_user_id=principal.user_id,
        payload={"academic_period_id": str(period.id)},
        metadata={"code": period.code, "status": period.status},
    )
    record_audit(
        session, institution_id=principal.institution_id,
        actor_user_id=principal.user_id, action="ACADEMIC_PERIOD_CREATED",
        entity_type="AcademicPeriod", entity_id=period.id,
        metadata={"code": period.code, "status": period.status},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Academic period code already exists") from exc
    session.refresh(period)
    return period


def transition_academic_period(
    session: Session,
    principal: CurrentPrincipal,
    period_id: UUID,
    *,
    expected_status: str,
    target_status: str,
) -> AcademicPeriod:
    require_academic_period_permission(session, principal, "academics.manage")
    period = session.exec(select(AcademicPeriod).where(
        AcademicPeriod.id == period_id,
        AcademicPeriod.organization_id == principal.organization_id,
        AcademicPeriod.institution_id == principal.institution_id,
    ).with_for_update()).first()
    if period is None:
        raise HTTPException(status_code=404, detail="Academic period not found")
    if period.status != expected_status:
        raise HTTPException(status_code=409, detail="Academic period changed; reload and retry")
    allowed = {"PLANNED": "ACTIVE", "ACTIVE": "CLOSED"}
    if allowed.get(period.status) != target_status:
        raise HTTPException(status_code=409, detail="Invalid academic period transition")
    if target_status == "CLOSED":
        active = session.exec(select(Enrollment.id).where(
            Enrollment.organization_id == principal.organization_id,
            Enrollment.institution_id == principal.institution_id,
            Enrollment.academic_period_id == period.id,
            Enrollment.status == "ACTIVE",
        ).limit(1)).first()
        if active is not None:
            raise HTTPException(status_code=409, detail="Resolve active enrollments before closing the period")
    previous = period.status
    period.status = target_status
    session.add(period)
    enqueue_canonical_event(
        session, institution_id=principal.institution_id,
        event_type="academic_period.status_changed", event_version=1,
        aggregate_type="academic_period", aggregate_id=period.id,
        actor_user_id=principal.user_id,
        payload={"academic_period_id": str(period.id), "previous_status": previous, "status": target_status},
        metadata={"expected_status": expected_status},
    )
    record_audit(
        session, institution_id=principal.institution_id,
        actor_user_id=principal.user_id, action="ACADEMIC_PERIOD_STATUS_CHANGED",
        entity_type="AcademicPeriod", entity_id=period.id,
        metadata={"previous_status": previous, "status": target_status},
    )
    session.commit()
    session.refresh(period)
    return period

_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"ACTIVE", "CANCELLED"}),
    "ACTIVE": frozenset({"WITHDRAWN", "COMPLETED"}),
    "WITHDRAWN": frozenset({"ACTIVE"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}


def available_enrollment_actions(enrollment: Enrollment) -> list[str]:
    return sorted(_TRANSITIONS.get(enrollment.status, frozenset()))


def require_enrollment_permission(session: Session, principal: CurrentPrincipal, key: str) -> None:
    if key not in {"enrollments.read", "enrollments.manage"}:
        raise ValueError("Unsupported enrollment permission")
    row = session.exec(
        text(
            """SELECT 1 FROM memberships m
            JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN roles r ON r.id=mr.role_id AND r.institution_id=m.institution_id
            JOIN role_permissions rp ON rp.role_id=mr.role_id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id=:user_id AND m.institution_id=:institution_id
              AND m.status='ACTIVE' AND p.key=:permission LIMIT 1"""
        ),
        params={"user_id": principal.user_id, "institution_id": principal.institution_id, "permission": key},
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Enrollment permission required")


def get_period_in_scope(session: Session, principal: CurrentPrincipal, period_id: UUID) -> AcademicPeriod:
    period = session.exec(
        select(AcademicPeriod).where(
            AcademicPeriod.id == period_id,
            AcademicPeriod.organization_id == principal.organization_id,
            AcademicPeriod.institution_id == principal.institution_id,
        )
    ).first()
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic period not found")
    return period


def _validate_effective_date(value: date | None, period: AcademicPeriod, *, required: bool) -> date | None:
    if value is None:
        if required:
            raise HTTPException(status_code=422, detail="An effective date is required")
        return None
    if value < period.starts_on or value > period.ends_on:
        raise HTTPException(status_code=422, detail="Effective date must fall within the academic period")
    return value


def create_enrollment_record(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
    academic_period_id: UUID,
    campus_id: UUID,
    enrollment_number: str | None,
    status_value: str,
    enrolled_on: date | None,
) -> Enrollment:
    """Create or replay the canonical enrollment; caller owns the transaction."""
    require_enrollment_permission(session, principal, "enrollments.manage")
    if status_value not in {"PENDING", "ACTIVE"}:
        raise HTTPException(status_code=422, detail="Unsupported initial enrollment state")
    student = session.exec(
        select(StudentProfile).where(
            StudentProfile.id == student_profile_id,
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
            StudentProfile.status == "ACTIVE",
        )
    ).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    period = get_period_in_scope(session, principal, academic_period_id)
    if period.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed academic periods are read-only")
    campus = session.exec(
        text("""SELECT 1 FROM campuses c JOIN institutions i ON i.id=c.institution_id
            WHERE c.id=:id AND c.institution_id=:inst AND i.organization_id=:org"""),
        params={"id": campus_id, "org": principal.organization_id, "inst": principal.institution_id},
    ).first()
    if campus is None:
        raise HTTPException(status_code=404, detail="Campus not found")
    effective_date = _validate_effective_date(enrolled_on, period, required=status_value == "ACTIVE")
    if status_value == "ACTIVE" and period.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Enrollment can only activate in an active academic period")

    existing = session.exec(
        select(Enrollment).where(
            Enrollment.organization_id == principal.organization_id,
            Enrollment.institution_id == principal.institution_id,
            Enrollment.student_profile_id == student_profile_id,
            Enrollment.academic_period_id == academic_period_id,
        ).with_for_update()
    ).first()
    if existing is not None:
        exact_replay = (
            existing.campus_id == campus_id
            and existing.enrollment_number == enrollment_number
            and existing.status == status_value
            and existing.enrolled_on == effective_date
        )
        if exact_replay:
            return existing
        raise HTTPException(status_code=409, detail="Enrollment already exists for this student and period")

    enrollment = Enrollment(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        student_profile_id=student_profile_id,
        academic_period_id=academic_period_id,
        campus_id=campus_id,
        enrollment_number=enrollment_number,
        status=status_value,
        enrolled_on=effective_date,
    )
    try:
        with session.begin_nested():
            session.add(enrollment)
            session.flush()
    except IntegrityError:
        replay = session.exec(
            select(Enrollment).where(
                Enrollment.organization_id == principal.organization_id,
                Enrollment.institution_id == principal.institution_id,
                Enrollment.student_profile_id == student_profile_id,
                Enrollment.academic_period_id == academic_period_id,
            )
        ).first()
        if replay is not None and (
            replay.campus_id, replay.enrollment_number, replay.status, replay.enrolled_on
        ) == (campus_id, enrollment_number, status_value, effective_date):
            return replay
        raise HTTPException(status_code=409, detail="Enrollment conflicts with an existing record") from None

    enqueue_canonical_event(
        session, institution_id=principal.institution_id,
        event_type="student.enrollment.created", event_version=1,
        aggregate_type="enrollment", aggregate_id=enrollment.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(student_profile_id),
            "academic_period_id": str(academic_period_id),
            "campus_id": str(campus_id), "status": status_value,
            "enrolled_on": effective_date.isoformat() if effective_date else None,
        },
    )
    record_audit(
        session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
        action="STUDENT_ENROLLMENT_CREATED", entity_type="Enrollment", entity_id=enrollment.id,
        metadata={"from_status": None, "to_status": status_value, "effective_on": effective_date.isoformat() if effective_date else None},
    )
    return enrollment


def transition_enrollment(
    session: Session,
    principal: CurrentPrincipal,
    enrollment_id: UUID,
    *,
    target_status: str,
    expected_updated_at: datetime,
    effective_on: date | None,
    reason_code: str | None,
) -> Enrollment:
    require_enrollment_permission(session, principal, "enrollments.manage")
    enrollment = session.exec(
        select(Enrollment).where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == principal.organization_id,
            Enrollment.institution_id == principal.institution_id,
        ).with_for_update()
    ).first()
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    period = get_period_in_scope(session, principal, enrollment.academic_period_id)
    if period.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed academic periods are read-only")

    # A retry after commit is a no-op even though its revision is stale.
    if enrollment.status == target_status:
        latest = session.exec(
            select(AuditLog).where(
                AuditLog.institution_id == principal.institution_id,
                AuditLog.entity_type == "Enrollment", AuditLog.entity_id == enrollment.id,
                AuditLog.action == "STUDENT_ENROLLMENT_STATUS_CHANGED",
            ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
        ).first()
        details = latest.metadata_json if latest is not None else {}
        requested_date = effective_on.isoformat() if effective_on else None
        current_date_matches = (
            (target_status == "WITHDRAWN" and enrollment.withdrawn_on == effective_on)
            or (target_status == "ACTIVE" and enrollment.enrolled_on == effective_on)
            or (target_status in {"COMPLETED", "CANCELLED"} and details.get("effective_on") == requested_date)
        )
        if (
            details.get("to_status") == target_status
            and details.get("effective_on") == requested_date
            and details.get("reason_code") == reason_code
            and current_date_matches
        ):
            return enrollment
    if enrollment.updated_at != expected_updated_at:
        raise HTTPException(status_code=409, detail="Enrollment changed; reload and retry")
    if target_status not in _TRANSITIONS.get(enrollment.status, frozenset()):
        raise HTTPException(status_code=409, detail="Invalid enrollment state transition")
    if (target_status in {"CANCELLED", "WITHDRAWN"} or (target_status == "ACTIVE" and enrollment.status == "WITHDRAWN")) and not reason_code:
        raise HTTPException(status_code=422, detail="A bounded reason code is required")

    prior_withdrawn_on = enrollment.withdrawn_on
    prior_enrolled_on = enrollment.enrolled_on
    if target_status == "ACTIVE":
        if period.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="Enrollment can only activate in an active academic period")
        effective_on = _validate_effective_date(effective_on, period, required=True)
        if enrollment.status == "WITHDRAWN":
            if prior_withdrawn_on is None or effective_on <= prior_withdrawn_on:
                raise HTTPException(status_code=422, detail="Reactivation must follow the recorded withdrawal date")
        enrollment.enrolled_on = effective_on
        enrollment.withdrawn_on = None
    elif target_status == "WITHDRAWN":
        effective_on = _validate_effective_date(effective_on, period, required=True)
        if enrollment.enrolled_on is None or effective_on < enrollment.enrolled_on:
            raise HTTPException(status_code=422, detail="Withdrawal cannot precede enrollment")
        enrollment.withdrawn_on = effective_on
    elif target_status == "COMPLETED":
        effective_on = _validate_effective_date(effective_on, period, required=True)
        if enrollment.enrolled_on is None or effective_on < enrollment.enrolled_on:
            raise HTTPException(status_code=422, detail="Completion cannot precede enrollment")
    elif target_status == "CANCELLED":
        if effective_on is not None:
            _validate_effective_date(effective_on, period, required=True)
        active_placement = session.exec(
            text("SELECT 1 FROM student_section_assignments WHERE enrollment_id=:id AND status='ACTIVE' LIMIT 1"),
            params={"id": enrollment.id},
        ).first()
        if active_placement is not None:
            raise HTTPException(status_code=409, detail="Close the active placement before cancelling enrollment")
    else:
        raise HTTPException(status_code=422, detail="Unsupported enrollment state")

    if target_status == "WITHDRAWN":
        session.exec(
            text("""UPDATE student_section_assignments
                SET status='WITHDRAWN', ended_on=:effective_on
                WHERE enrollment_id=:enrollment_id AND institution_id=:institution_id
                  AND status='ACTIVE' AND assigned_on <= :effective_on"""),
            params={"effective_on": effective_on, "enrollment_id": enrollment.id, "institution_id": principal.institution_id},
        )
        remaining = session.exec(
            text("SELECT 1 FROM student_section_assignments WHERE enrollment_id=:id AND status='ACTIVE' LIMIT 1"),
            params={"id": enrollment.id},
        ).first()
        if remaining is not None:
            raise HTTPException(status_code=409, detail="Withdrawal date precedes the active placement")

    previous_status = enrollment.status
    enrollment.status = target_status
    enrollment.updated_at = datetime.now(UTC)
    session.add(enrollment)
    metadata = {
        "from_status": previous_status, "to_status": target_status,
        "effective_on": effective_on.isoformat() if effective_on else None,
        "reason_code": reason_code, "previous_withdrawn_on": prior_withdrawn_on.isoformat() if prior_withdrawn_on else None,
        "previous_enrolled_on": prior_enrolled_on.isoformat() if prior_enrolled_on else None,
        "permission": "enrollments.manage",
    }
    record_audit(
        session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
        action="STUDENT_ENROLLMENT_STATUS_CHANGED", entity_type="Enrollment", entity_id=enrollment.id,
        metadata=metadata,
    )
    enqueue_canonical_event(
        session, institution_id=principal.institution_id,
        event_type="student.enrollment.status_changed", event_version=1,
        aggregate_type="enrollment", aggregate_id=enrollment.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(enrollment.student_profile_id),
            "academic_period_id": str(enrollment.academic_period_id),
            "previous_status": previous_status, "status": enrollment.status,
            "withdrawn_on": enrollment.withdrawn_on.isoformat() if enrollment.withdrawn_on else None,
            "effective_on": effective_on.isoformat() if effective_on else None,
            "reason_code": reason_code,
            "previous_withdrawn_on": prior_withdrawn_on.isoformat() if prior_withdrawn_on else None,
            "previous_enrolled_on": prior_enrolled_on.isoformat() if prior_enrolled_on else None,
        },
    )
    return enrollment


def enrollment_history(session: Session, principal: CurrentPrincipal, enrollment_id: UUID) -> list[AuditLog]:
    require_enrollment_permission(session, principal, "enrollments.read")
    visible = session.exec(
        select(Enrollment.id).where(
            Enrollment.id == enrollment_id,
            Enrollment.organization_id == principal.organization_id,
            Enrollment.institution_id == principal.institution_id,
        )
    ).first()
    if visible is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    return session.exec(
        select(AuditLog).where(
            AuditLog.institution_id == principal.institution_id,
            AuditLog.entity_type == "Enrollment", AuditLog.entity_id == enrollment_id,
            AuditLog.action.in_(["STUDENT_ENROLLMENT_CREATED", "STUDENT_ENROLLMENT_STATUS_CHANGED"]),
        ).order_by(AuditLog.created_at, AuditLog.id)
    ).all()
