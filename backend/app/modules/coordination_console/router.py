from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.api.access import (
    require_coordination_analytics,
    require_coordination_cases,
    require_coordination_signals,
)
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.automation.schemas import (
    AutomationTaskRead,
    EngineRunResult,
    EngineTickResult,
    TaskComplete,
    TimelineEventRead,
)
from app.modules.coordination_console.schemas import (
    AttentionItem,
    CaseWorkspaceItem,
    CoordinationSummary,
)
from app.modules.coordination_console.service import (
    acknowledge_coordination_task,
    attention_queue,
    case_workspace,
    complete_coordination_task,
    coordination_academic_trend,
    coordination_attendance_trend,
    coordination_case_timeline,
    coordination_sections,
    coordination_summary,
    refresh_coordination_signals,
    resolve_coordination_signal,
    run_coordination_engine,
    tick_coordination_engine,
)
from app.modules.intelligence.schemas import (
    AcademicTrendPoint,
    AttendanceTrendPoint,
    SectionIntelligence,
    SignalRead,
    SignalRefreshResult,
    SignalResolve,
)

router = APIRouter(prefix="/coordination", tags=["rector-coordination-console"])
AnalyticsPrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_coordination_analytics),
]
SignalsPrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_coordination_signals),
]
CasesPrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_coordination_cases),
]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def coordination_dashboard_html():
    path = Path(__file__).with_name("coordination_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/summary", response_model=CoordinationSummary)
def summary(_: AnalyticsPrincipalDep, session: SessionDep):
    return coordination_summary(session)


@router.get("/attention", response_model=list[AttentionItem])
def attention(_: AnalyticsPrincipalDep, session: SessionDep):
    return attention_queue(session)


@router.get("/sections", response_model=list[SectionIntelligence])
def sections(_: AnalyticsPrincipalDep, session: SessionDep):
    return coordination_sections(session)


@router.get(
    "/trends/attendance",
    response_model=list[AttendanceTrendPoint],
)
def attendance_trend(
    _: AnalyticsPrincipalDep,
    session: SessionDep,
    days: int = Query(default=30, ge=7, le=365),
):
    return coordination_attendance_trend(session, days)


@router.get(
    "/trends/academic",
    response_model=list[AcademicTrendPoint],
)
def academic_trend(_: AnalyticsPrincipalDep, session: SessionDep):
    return coordination_academic_trend(session)


@router.get("/cases", response_model=list[CaseWorkspaceItem])
def cases(_: CasesPrincipalDep, session: SessionDep):
    return case_workspace(session)


@router.get(
    "/cases/{case_id}/timeline",
    response_model=list[TimelineEventRead],
)
def case_timeline(
    case_id: UUID,
    _: CasesPrincipalDep,
    session: SessionDep,
):
    return coordination_case_timeline(session, case_id)


@router.post(
    "/signals/refresh",
    response_model=SignalRefreshResult,
)
def signals_refresh(
    principal: SignalsPrincipalDep,
    session: SessionDep,
):
    return refresh_coordination_signals(session, principal)


@router.post(
    "/signals/{signal_id}/resolve",
    response_model=SignalRead,
)
def signal_resolve(
    signal_id: UUID,
    payload: SignalResolve,
    principal: SignalsPrincipalDep,
    session: SessionDep,
):
    return resolve_coordination_signal(
        session,
        principal,
        signal_id,
        payload,
    )


@router.post(
    "/workflows/run",
    response_model=EngineRunResult,
)
def workflows_run(
    principal: CasesPrincipalDep,
    session: SessionDep,
):
    return run_coordination_engine(session, principal)


@router.post(
    "/workflows/tick",
    response_model=EngineTickResult,
)
def workflows_tick(
    principal: CasesPrincipalDep,
    session: SessionDep,
):
    return tick_coordination_engine(session, principal)


@router.post(
    "/tasks/{task_id}/acknowledge",
    response_model=AutomationTaskRead,
)
def task_acknowledge(
    task_id: UUID,
    principal: CasesPrincipalDep,
    session: SessionDep,
):
    return acknowledge_coordination_task(
        session,
        principal,
        task_id,
    )


@router.post(
    "/tasks/{task_id}/complete",
    response_model=AutomationTaskRead,
)
def task_complete(
    task_id: UUID,
    payload: TaskComplete,
    principal: CasesPrincipalDep,
    session: SessionDep,
):
    return complete_coordination_task(
        session,
        principal,
        task_id,
        payload,
    )
