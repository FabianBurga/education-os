from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.students.models import StudentProfile


def create_student_profile(
    session: Session,
    principal: CurrentPrincipal,
    *,
    person_id: UUID,
    student_code: str | None,
) -> StudentProfile:
    """Canonical student-create command. Caller owns transaction boundaries."""
    if session.exec(text("SELECT id FROM persons WHERE id = :person_id").bindparams(person_id=person_id)).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found in current tenant")
    student = StudentProfile(organization_id=principal.organization_id, institution_id=principal.institution_id,
                             person_id=person_id, student_code=student_code)
    session.add(student)
    return student


def update_student_profile(session: Session, student_id: UUID, changes: dict[str, object]) -> StudentProfile:
    """Canonical student-update command. Caller owns transaction boundaries."""
    student = session.get(StudentProfile, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    for key, value in changes.items():
        setattr(student, key, value)
    session.add(student)
    return student
