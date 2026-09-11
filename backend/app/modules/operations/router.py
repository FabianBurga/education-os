from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.access import (
    require_privileged_staff_access,
    require_staff_access,
)
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.operations.schemas import (
    PilotDataSummary,
    PilotReadinessResult,
    PilotReadinessRunRead,
    SecurityBaseline,
)
from app.modules.operations.service import (
    latest_pilot_readiness,
    pilot_data_summary,
    run_pilot_readiness,
    security_baseline,
)

router = APIRouter(
    prefix="/operations",
    tags=["operations"],
    dependencies=[
        Depends(require_staff_access),
        Depends(require_privileged_staff_access),
    ],
)

SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[CurrentPrincipal, Depends(require_staff_access)]


@router.get("/security-baseline", response_model=SecurityBaseline)
def get_security_baseline(_: StaffDep, session: SessionDep):
    return security_baseline(session)


@router.get("/pilot/data-summary", response_model=PilotDataSummary)
def get_pilot_data_summary(_: StaffDep, session: SessionDep):
    return pilot_data_summary(session)


@router.post("/pilot/readiness/run", response_model=PilotReadinessResult)
def execute_pilot_readiness(principal: StaffDep, session: SessionDep):
    return run_pilot_readiness(session, principal)


@router.get(
    "/pilot/readiness/latest",
    response_model=PilotReadinessRunRead | None,
)
def get_latest_pilot_readiness(_: StaffDep, session: SessionDep):
    return latest_pilot_readiness(session)
