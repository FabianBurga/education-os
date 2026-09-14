from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.access import require_student_timeline_read
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.student_timeline.schemas import StudentTimelinePage
from app.modules.student_timeline.service import list_student_timeline

router = APIRouter(
    prefix="/student-timeline",
    tags=["student-timeline"],
)

TimelinePrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_student_timeline_read),
]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/students/{student_profile_id}",
    response_model=StudentTimelinePage,
)
def student_timeline(
    student_profile_id: UUID,
    _: TimelinePrincipalDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    before_position: int | None = Query(default=None, ge=1),
    category: str | None = Query(default=None, max_length=32),
    sensitivity: str | None = Query(default=None, max_length=20),
):
    try:
        return list_student_timeline(
            session,
            student_profile_id=student_profile_id,
            limit=limit,
            before_position=before_position,
            category=category,
            sensitivity=sensitivity,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc