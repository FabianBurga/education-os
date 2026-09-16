from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal
from app.modules.enrollment.models import Enrollment
from app.modules.events.service import enqueue_canonical_event
from app.modules.students.models import StudentProfile


def create_enrollment_record(
    session: Session,
    principal: CurrentPrincipal,
    *,
    student_profile_id: UUID,
    academic_period_id: UUID,
    campus_id: UUID,
    enrollment_number: str | None,
    status_value: str,
    enrolled_on: object,
) -> Enrollment:
    """Canonical enrollment-create command. Caller owns transaction boundaries."""
    if session.get(StudentProfile, student_profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    if session.exec(text("SELECT id FROM academic_periods WHERE id = :id").bindparams(id=academic_period_id)).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic period not found")
    if session.exec(text("SELECT id FROM campuses WHERE id = :id").bindparams(id=campus_id)).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campus not found")
    enrollment = Enrollment(organization_id=principal.organization_id, institution_id=principal.institution_id,
                            student_profile_id=student_profile_id, academic_period_id=academic_period_id, campus_id=campus_id,
                            enrollment_number=enrollment_number, status=status_value, enrolled_on=enrolled_on)
    session.add(enrollment)
    enqueue_canonical_event(session, institution_id=principal.institution_id, event_type="student.enrollment.created",
                            event_version=1, aggregate_type="enrollment", aggregate_id=enrollment.id,
                            actor_user_id=principal.user_id,
                            payload={"student_profile_id": str(enrollment.student_profile_id),
                                     "academic_period_id": str(enrollment.academic_period_id), "campus_id": str(enrollment.campus_id),
                                     "status": enrollment.status,
                                     "enrolled_on": enrollment.enrolled_on.isoformat() if enrollment.enrolled_on is not None else None})
    return enrollment
