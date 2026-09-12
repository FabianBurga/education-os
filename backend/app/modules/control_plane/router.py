from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.db.session import get_session
from app.modules.control_plane.schemas import (
    CapabilityControlRead,
    CapabilityControlUpdate,
    ControlChangeRead,
    ControlPlaneSummary,
    PolicyControlRead,
    PolicyControlUpdate,
)
from app.modules.control_plane.security import (
    ControlPlaneManageDep,
    ControlPlaneViewDep,
)
from app.modules.control_plane.service import (
    control_plane_summary,
    list_capabilities,
    list_changes,
    list_policies,
    update_capability,
    update_policy,
)

router = APIRouter(
    prefix="/control-plane",
    tags=["institution-control-plane"],
)
SessionDep = Annotated[Session, Depends(get_session)]


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def control_plane_dashboard_html():
    path = Path(__file__).with_name("control_plane_dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@router.get("/summary", response_model=ControlPlaneSummary)
def summary(
    principal: ControlPlaneViewDep,
    session: SessionDep,
):
    return control_plane_summary(session, principal)


@router.get(
    "/capabilities",
    response_model=list[CapabilityControlRead],
)
def capabilities(
    principal: ControlPlaneViewDep,
    session: SessionDep,
):
    return list_capabilities(session, principal)


@router.put(
    "/capabilities/{capability_key}",
    response_model=CapabilityControlRead,
)
def capability_update(
    capability_key: str,
    payload: CapabilityControlUpdate,
    principal: ControlPlaneManageDep,
    session: SessionDep,
):
    return update_capability(
        session,
        principal,
        capability_key,
        payload,
    )


@router.get(
    "/policies",
    response_model=list[PolicyControlRead],
)
def policies(
    principal: ControlPlaneViewDep,
    session: SessionDep,
):
    return list_policies(session, principal)


@router.put(
    "/policies/{policy_key}",
    response_model=PolicyControlRead,
)
def policy_update(
    policy_key: str,
    payload: PolicyControlUpdate,
    principal: ControlPlaneManageDep,
    session: SessionDep,
):
    return update_policy(
        session,
        principal,
        policy_key,
        payload,
    )


@router.get(
    "/changes",
    response_model=list[ControlChangeRead],
)
def changes(
    principal: ControlPlaneViewDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
):
    return list_changes(
        session,
        principal,
        limit=limit,
    )
