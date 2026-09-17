from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.agents.schemas import (
    AgentDefinitionRead,
    AgentEvidenceRead,
    AgentRunCreate,
    AgentRunRead,
    AgentRunStepRead,
    AgentToolCallRead,
)
from app.modules.agents.service import (
    get_agent_run,
    list_agent_definitions,
    list_agent_evidence,
    list_agent_runs,
    list_agent_steps,
    list_agent_tool_calls,
    run_integration_run_advisor,
)

router = APIRouter(prefix="/agents", tags=["agents"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[AgentDefinitionRead])
def agents(principal: PrincipalDep, session: SessionDep):
    return list_agent_definitions(session, principal)


@router.post("/integration_run_advisor/runs", response_model=AgentRunRead, status_code=status.HTTP_201_CREATED)
def integration_run_advisor(payload: AgentRunCreate, principal: PrincipalDep, session: SessionDep):
    result = run_integration_run_advisor(session, principal, integration_run_id=payload.integration_run_id)
    session.commit()
    return result


@router.get("/runs", response_model=list[AgentRunRead])
def runs(principal: PrincipalDep, session: SessionDep, limit: int = Query(default=100, ge=1, le=100)):
    return list_agent_runs(session, principal, limit=limit)


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def run(run_id: UUID, principal: PrincipalDep, session: SessionDep):
    return get_agent_run(session, principal, run_id)


@router.get("/runs/{run_id}/steps", response_model=list[AgentRunStepRead])
def steps(run_id: UUID, principal: PrincipalDep, session: SessionDep):
    return list_agent_steps(session, principal, run_id)


@router.get("/runs/{run_id}/evidence", response_model=list[AgentEvidenceRead])
def evidence(run_id: UUID, principal: PrincipalDep, session: SessionDep):
    return list_agent_evidence(session, principal, run_id)


@router.get("/runs/{run_id}/tool-calls", response_model=list[AgentToolCallRead])
def tool_calls(run_id: UUID, principal: PrincipalDep, session: SessionDep):
    return list_agent_tool_calls(session, principal, run_id)
