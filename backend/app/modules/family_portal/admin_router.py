from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.access import (
    require_privileged_staff_access,
    require_staff_access,
)
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.family_portal.schemas import (
    BootstrapAccessResult,
    FamilyNoticeCreate,
    PortalGrantCreate,
    PortalGrantRead,
    StaffNoticeRead,
)
from app.modules.family_portal.service import (
    bootstrap_grants,
    create_grant,
    create_notice,
    publish_notice,
    revoke_grant,
)

router = APIRouter(
    prefix="/family-admin",
    tags=["family-admin"],
    dependencies=[Depends(require_privileged_staff_access)],
)
SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[CurrentPrincipal, Depends(require_staff_access)]


@router.post("/access/bootstrap", response_model=BootstrapAccessResult)
def access_bootstrap(principal: StaffDep, session: SessionDep):
    return bootstrap_grants(session, principal)


@router.post("/access/grants", response_model=PortalGrantRead, status_code=201)
def access_grant(
    payload: PortalGrantCreate,
    principal: StaffDep,
    session: SessionDep,
):
    return create_grant(session, principal, payload)


@router.post("/access/grants/{grant_id}/revoke", response_model=PortalGrantRead)
def access_revoke(grant_id: UUID, _: StaffDep, session: SessionDep):
    return revoke_grant(session, grant_id)


@router.post("/notices", response_model=StaffNoticeRead, status_code=201)
def notices_create(
    payload: FamilyNoticeCreate,
    principal: StaffDep,
    session: SessionDep,
):
    return create_notice(session, principal, payload)


@router.post("/notices/{notice_id}/publish", response_model=StaffNoticeRead)
def notices_publish(notice_id: UUID, _: StaffDep, session: SessionDep):
    return publish_notice(session, notice_id)
