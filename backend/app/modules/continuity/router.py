from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.access import require_staff_access
from app.api.deps import CurrentPrincipal
from app.db.session import get_session

from .schemas import ContinuityWorklistRead
from .service import get_continuity_worklist

router = APIRouter(prefix="/continuity", tags=["m29-continuity"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(require_staff_access)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/worklist", response_model=ContinuityWorklistRead)
def worklist(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
) -> ContinuityWorklistRead:
    return get_continuity_worklist(session, principal, limit=limit)

