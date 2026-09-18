from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    InstitutionIntelligenceAgentRunCreate,
    IntegrationRunExplainerCreate,
    StudentTimelineAgentRunCreate,
)
from app.modules.agents.service import (
    get_agent_run,
    list_agent_definitions,
    list_agent_evidence,
    list_agent_runs,
    list_agent_steps,
    list_agent_tool_calls,
    run_institution_intelligence_advisor,
    run_integration_run_advisor,
    run_integration_run_explainer,
    run_student_timeline_advisor,
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


@router.post("/{agent_key}/runs", response_model=AgentRunRead, status_code=status.HTTP_201_CREATED)
def advisor_run(
    agent_key: str,
    payload: AgentRunCreate | StudentTimelineAgentRunCreate | InstitutionIntelligenceAgentRunCreate | IntegrationRunExplainerCreate,
    principal: PrincipalDep,
    session: SessionDep,
):
    if agent_key == "integration_run_advisor" and isinstance(payload, AgentRunCreate):
        result = run_integration_run_advisor(session, principal, integration_run_id=payload.integration_run_id)
    elif agent_key == "student_timeline_advisor" and isinstance(payload, StudentTimelineAgentRunCreate):
        result = run_student_timeline_advisor(session, principal, student_id=payload.student_id)
    elif agent_key == "institution_intelligence_advisor" and isinstance(payload, InstitutionIntelligenceAgentRunCreate):
        result = run_institution_intelligence_advisor(session, principal)
    elif agent_key == "integration_run_explainer" and isinstance(payload, IntegrationRunExplainerCreate):
        result = run_integration_run_explainer(
            session,
            principal,
            integration_run_id=payload.integration_run_id,
            explanation_focus=payload.explanation_focus,
        )
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Typed agent input does not match agent")
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
