from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.access import require_student_record_permission
from app.api.deps import CurrentPrincipal
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event
from app.modules.students.models import StudentProfile


def get_student_in_scope(
    session: Session,
    principal: CurrentPrincipal,
    student_id: UUID,
    *,
    lock: bool = False,
) -> StudentProfile:
    statement = select(StudentProfile).where(
        StudentProfile.id == student_id,
        StudentProfile.organization_id == principal.organization_id,
        StudentProfile.institution_id == principal.institution_id,
    )
    if lock:
        statement = statement.with_for_update()
    student = session.exec(statement).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def create_student_profile(
    session: Session,
    principal: CurrentPrincipal,
    *,
    person_id: UUID,
    student_code: str | None,
    source: Literal["STUDENT_API", "M24_IMPORT"] = "STUDENT_API",
) -> tuple[StudentProfile, bool]:
    """Create the authoritative profile; caller owns the enclosing transaction."""
    require_student_record_permission(session, principal, "students.manage")
    if source not in {"STUDENT_API", "M24_IMPORT"}:
        raise ValueError("Unsupported student creation source")
    person = session.exec(
        text(
            "SELECT id FROM persons WHERE id = :person_id "
            "AND organization_id = :organization_id"
        ).bindparams(person_id=person_id, organization_id=principal.organization_id)
    ).first()
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    existing = session.exec(
        select(StudentProfile).where(
            StudentProfile.person_id == person_id,
            StudentProfile.organization_id == principal.organization_id,
            StudentProfile.institution_id == principal.institution_id,
        )
    ).first()
    if existing is not None:
        if existing.student_code != student_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student profile already exists with different record data",
            )
        return existing, False

    student = StudentProfile(
        organization_id=principal.organization_id,
        institution_id=principal.institution_id,
        person_id=person_id,
        student_code=student_code,
    )
    try:
        with session.begin_nested():
            session.add(student)
            session.flush()
    except IntegrityError:
        existing = session.exec(
            select(StudentProfile).where(
                StudentProfile.person_id == person_id,
                StudentProfile.organization_id == principal.organization_id,
                StudentProfile.institution_id == principal.institution_id,
            )
        ).first()
        if existing is not None and existing.student_code == student_code:
            return existing, False
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student profile conflicts with an existing record",
        ) from None
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.profile.created",
        event_version=1,
        aggregate_type="student_profile",
        aggregate_id=student.id,
        actor_user_id=principal.user_id,
        payload={"student_profile_id": str(student.id)},
        metadata={"source": source},
    )
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="STUDENT_PROFILE_CREATED",
        entity_type="StudentProfile",
        entity_id=student.id,
        metadata={"source": source, "permission": "students.manage"},
    )
    return student, True


def update_student_profile(
    session: Session,
    principal: CurrentPrincipal,
    student_id: UUID,
    changes: dict[str, object],
    *,
    expected_updated_at: datetime,
) -> StudentProfile:
    """Apply an allowlisted, optimistic update with atomic audit and event."""
    require_student_record_permission(session, principal, "students.manage")
    allowed_fields = {"student_code", "status"}
    if not changes or set(changes) - allowed_fields:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid student fields")
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Student status cannot be null")
    student = get_student_in_scope(session, principal, student_id, lock=True)
    if student.updated_at != expected_updated_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student record changed; reload and retry")

    next_status = changes.get("status", student.status)
    if next_status != "ACTIVE":
        active_enrollment = session.exec(
            text(
                "SELECT 1 FROM enrollments WHERE student_profile_id = :student_id "
                "AND institution_id = :institution_id AND status = 'ACTIVE' LIMIT 1"
            ).bindparams(student_id=student.id, institution_id=principal.institution_id)
        ).first()
        if active_enrollment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Resolve the active enrollment before changing student status",
            )

    for key, value in changes.items():
        setattr(student, key, value)
    student.updated_at = datetime.now(UTC)
    session.add(student)
    enqueue_canonical_event(
        session,
        institution_id=principal.institution_id,
        event_type="student.profile.updated",
        event_version=1,
        aggregate_type="student_profile",
        aggregate_id=student.id,
        actor_user_id=principal.user_id,
        payload={
            "student_profile_id": str(student.id),
            "changed_fields": sorted(changes),
        },
        metadata={"permission": "students.manage"},
    )
    record_audit(
        session,
        institution_id=principal.institution_id,
        actor_user_id=principal.user_id,
        action="STUDENT_PROFILE_UPDATED",
        entity_type="StudentProfile",
        entity_id=student.id,
        metadata={"changed_fields": sorted(changes), "permission": "students.manage"},
    )
    return student
