from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.integrations.schemas import (
    IntegrationConnectorCreate,
    IntegrationConnectorRead,
    IntegrationRunRead,
)
from app.modules.integrations.service import (
    create_connector,
    get_connector,
    get_run,
    list_connectors,
    list_runs,
    set_connector_status,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/connectors", response_model=list[IntegrationConnectorRead])
def connectors(principal: PrincipalDep, session: SessionDep):
    return list_connectors(session, principal)


@router.post("/connectors", response_model=IntegrationConnectorRead, status_code=status.HTTP_201_CREATED)
def connector_create(payload: IntegrationConnectorCreate, principal: PrincipalDep, session: SessionDep):
    result = create_connector(session, principal, payload)
    session.commit()
    return result


@router.get("/connectors/{connector_id}", response_model=IntegrationConnectorRead)
def connector_get(connector_id: UUID, principal: PrincipalDep, session: SessionDep):
    return get_connector(session, principal, connector_id)


@router.post("/connectors/{connector_id}/disable", response_model=IntegrationConnectorRead)
def connector_disable(connector_id: UUID, principal: PrincipalDep, session: SessionDep):
    result = set_connector_status(session, principal, connector_id, "DISABLED")
    session.commit()
    return result


@router.post("/connectors/{connector_id}/enable", response_model=IntegrationConnectorRead)
def connector_enable(connector_id: UUID, principal: PrincipalDep, session: SessionDep):
    result = set_connector_status(session, principal, connector_id, "ENABLED")
    session.commit()
    return result


@router.get("/runs", response_model=list[IntegrationRunRead])
def runs(principal: PrincipalDep, session: SessionDep):
    return list_runs(session, principal)


@router.get("/runs/{run_id}", response_model=IntegrationRunRead)
def run_get(run_id: UUID, principal: PrincipalDep, session: SessionDep):
    return get_run(session, principal, run_id)
