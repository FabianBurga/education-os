from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.intelligence.schemas import (
    AcademicTrendPoint,
    AttendanceTrendPoint,
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
def rector_overview_api(_: PrincipalDep, session: SessionDep):
    return rector_overview(session)


@router.get("/rector/sections", response_model=list[SectionIntelligence])
def rector_sections_api(_: PrincipalDep, session: SessionDep):
    return section_drilldown(session)


@router.get("/rector/trends/attendance", response_model=list[AttendanceTrendPoint])
def rector_attendance_trend_api(
    _: PrincipalDep,
    session: SessionDep,
    days: int = Query(default=30, ge=7, le=365),
):
    return attendance_trend(session, days=days)


@router.get("/rector/trends/academic", response_model=list[AcademicTrendPoint])
def rector_academic_trend_api(_: PrincipalDep, session: SessionDep):
    return academic_trend(session)


@router.get("/signals", response_model=list[SignalRead])
def signals_list_api(
    _: PrincipalDep,
    session: SessionDep,
    status: str = Query(default="OPEN", pattern="^(OPEN|RESOLVED|CLOSED)$"),
):
    return list_signals(session, status=status)


@router.post("/signals/refresh", response_model=SignalRefreshResult)
def signals_refresh_api(principal: PrincipalDep, session: SessionDep):
    return refresh_signals(session, principal)


@router.post("/signals/{signal_id}/resolve", response_model=SignalRead)
def signals_resolve_api(
    signal_id: UUID,
    payload: SignalResolve,
    _: PrincipalDep,
    session: SessionDep,
):
    return resolve_signal(session, signal_id, payload)


@router.get(
    "/rector/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def rector_dashboard_html():
    path = Path(__file__).with_name("rector_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))
