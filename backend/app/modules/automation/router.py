from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.automation.schemas import (
    AutomationCaseRead,
    AutomationRuleCreate,
    AutomationRuleRead,
    AutomationTaskRead,
    BootstrapRulesResult,
    EngineRunResult,
    EngineTickResult,
    TaskComplete,
    TimelineEventRead,
)
from app.modules.automation.service import (
    acknowledge_task,
    bootstrap_default_rules,
    complete_task,
    create_rule,
    get_case,
    list_case_tasks,
    list_case_timeline,
    list_cases,
    list_rules,
    run_engine,
    tick_engine,
)

router = APIRouter(prefix="/automation", tags=["automation"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/rules", response_model=list[AutomationRuleRead])
def rules_list(_: PrincipalDep, session: SessionDep):
    return list_rules(session)


@router.post("/rules", response_model=AutomationRuleRead, status_code=201)
def rules_create(
    payload: AutomationRuleCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    return create_rule(session, principal, payload)


@router.post("/rules/bootstrap-defaults", response_model=BootstrapRulesResult)
def rules_bootstrap(principal: PrincipalDep, session: SessionDep):
    return bootstrap_default_rules(session, principal)


@router.post("/engine/run", response_model=EngineRunResult)
def engine_run(principal: PrincipalDep, session: SessionDep):
    return run_engine(session, principal)


@router.post("/engine/tick", response_model=EngineTickResult)
def engine_tick(principal: PrincipalDep, session: SessionDep):
    return tick_engine(session, principal)


@router.get("/cases", response_model=list[AutomationCaseRead])
def cases_list(_: PrincipalDep, session: SessionDep):
    return list_cases(session)


@router.get("/cases/{case_id}", response_model=AutomationCaseRead)
def cases_get(case_id: UUID, _: PrincipalDep, session: SessionDep):
    return get_case(session, case_id)


@router.get("/cases/{case_id}/tasks", response_model=list[AutomationTaskRead])
def case_tasks(case_id: UUID, _: PrincipalDep, session: SessionDep):
    return list_case_tasks(session, case_id)


@router.get(
    "/cases/{case_id}/timeline",
    response_model=list[TimelineEventRead],
)
def case_timeline(case_id: UUID, _: PrincipalDep, session: SessionDep):
    return list_case_timeline(session, case_id)


@router.post(
    "/tasks/{task_id}/acknowledge",
    response_model=AutomationTaskRead,
)
def task_acknowledge(
    task_id: UUID,
    principal: PrincipalDep,
    session: SessionDep,
):
    return acknowledge_task(session, principal, task_id)


@router.post(
    "/tasks/{task_id}/complete",
    response_model=AutomationTaskRead,
)
def task_complete(
    task_id: UUID,
    payload: TaskComplete,
    principal: PrincipalDep,
    session: SessionDep,
):
    return complete_task(session, principal, task_id, payload)
