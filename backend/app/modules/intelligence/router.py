from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.intelligence.access import (
    require_intelligence_manage,
    require_intelligence_manager_read,
    require_intelligence_read,
)
from app.modules.intelligence.decision_surfaces import (
    intelligence_overview,
    intelligence_trends,
    intervention_health,
    list_intelligence_cohorts,
    list_intelligence_priorities,
)
from app.modules.intelligence.schemas import (
    AcademicTrendPoint,
    AttendanceTrendPoint,
    CohortIntelligenceRead,
    IntelligenceOverviewRead,
    IntelligencePriorityItem,
    IntelligenceTrendPoint,
    InterventionHealthRead,
    RectorOverview,
    SectionIntelligence,
    SignalRead,
    SignalRefreshResult,
    SignalResolve,
)
from app.modules.intelligence.service import (
    academic_trend,
    attendance_trend,
    list_signals,
    rector_overview,
    refresh_signals,
    resolve_signal,
    section_drilldown,
)

router = APIRouter(prefix="/intelligence", tags=["rector-intelligence"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/rector/overview", response_model=RectorOverview)
def rector_overview_api(principal: PrincipalDep, session: SessionDep):
    require_intelligence_manager_read(session, principal)
    return rector_overview(session)


@router.get("/rector/sections", response_model=list[SectionIntelligence])
def rector_sections_api(principal: PrincipalDep, session: SessionDep):
    require_intelligence_manager_read(session, principal)
    return section_drilldown(session)


@router.get("/rector/trends/attendance", response_model=list[AttendanceTrendPoint])
def rector_attendance_trend_api(
    principal: PrincipalDep,
    session: SessionDep,
    days: int = Query(default=30, ge=7, le=365),
):
    require_intelligence_manager_read(session, principal)
    return attendance_trend(session, days=days)


@router.get("/rector/trends/academic", response_model=list[AcademicTrendPoint])
def rector_academic_trend_api(
    principal: PrincipalDep,
    session: SessionDep,
):
    require_intelligence_manager_read(session, principal)
    return academic_trend(session)


@router.get("/signals", response_model=list[SignalRead])
def signals_list_api(
    principal: PrincipalDep,
    session: SessionDep,
    status: str = Query(default="OPEN", pattern="^(OPEN|RESOLVED|CLOSED)$"),
):
    require_intelligence_read(session, principal)
    return list_signals(session, status=status)


@router.post("/signals/refresh", response_model=SignalRefreshResult)
def signals_refresh_api(principal: PrincipalDep, session: SessionDep):
    require_intelligence_manage(session, principal)
    return refresh_signals(session, principal)


@router.post("/signals/{signal_id}/resolve", response_model=SignalRead)
def signals_resolve_api(
    signal_id: UUID,
    payload: SignalResolve,
    principal: PrincipalDep,
    session: SessionDep,
):
    require_intelligence_manage(session, principal)
    return resolve_signal(session, principal, signal_id, payload)


@router.get("/overview", response_model=IntelligenceOverviewRead)
def intelligence_overview_api(
    principal: PrincipalDep,
    session: SessionDep,
):
    return intelligence_overview(session, principal)


@router.get("/priorities", response_model=list[IntelligencePriorityItem])
def intelligence_priorities_api(
    principal: PrincipalDep,
    session: SessionDep,
    academic_period_id: UUID | None = Query(default=None),
    snapshot_date: date | None = Query(default=None),
    priority: Literal["LOW", "MEDIUM", "HIGH"] | None = Query(default=None),
    dimension: Literal["ATTENDANCE", "ACADEMIC", "INTERVENTION"] | None = Query(
        default=None
    ),
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_intelligence_priorities(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
        priority=priority,
        dimension=dimension,
        limit=limit,
    )


@router.get("/cohorts", response_model=list[CohortIntelligenceRead])
def intelligence_cohorts_api(
    principal: PrincipalDep,
    session: SessionDep,
    academic_period_id: UUID | None = Query(default=None),
    snapshot_date: date | None = Query(default=None),
    cohort_type: Literal[
        "INSTITUTION",
        "ACADEMIC_LEVEL",
        "GRADE",
        "SECTION",
        "COURSE",
    ]
    | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
):
    return list_intelligence_cohorts(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
        cohort_type=cohort_type,
        limit=limit,
    )


@router.get("/trends", response_model=list[IntelligenceTrendPoint])
def intelligence_trends_api(
    principal: PrincipalDep,
    session: SessionDep,
    academic_period_id: UUID | None = Query(default=None),
    days: int = Query(default=30, ge=2, le=365),
):
    return intelligence_trends(
        session,
        principal,
        academic_period_id=academic_period_id,
        days=days,
    )


@router.get("/interventions", response_model=InterventionHealthRead)
def intelligence_interventions_api(
    principal: PrincipalDep,
    session: SessionDep,
    academic_period_id: UUID | None = Query(default=None),
    snapshot_date: date | None = Query(default=None),
):
    return intervention_health(
        session,
        principal,
        academic_period_id=academic_period_id,
        snapshot_date=snapshot_date,
    )


@router.get(
    "/rector/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def rector_dashboard_html():
    path = Path(__file__).with_name("rector_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))
