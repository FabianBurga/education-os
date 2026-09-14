from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.api.access import (
    require_intervention_action_manage,
    require_intervention_assign,
    require_intervention_close,
    require_intervention_create,
    require_intervention_followup_create,
    require_intervention_read,
    require_intervention_resolve,
    require_intervention_update,
)
from app.api.deps import CurrentPrincipal
from app.db.session import get_session
from app.modules.interventions.schemas import (
    InterventionActionAssign,
    InterventionActionComplete,
    InterventionActionCreate,
    InterventionActionPage,
    InterventionActionRead,
    InterventionActionTransition,
    InterventionAssign,
    InterventionCancel,
    InterventionClose,
    InterventionCreate,
    InterventionFollowUpCreate,
    InterventionFollowUpPage,
    InterventionFollowUpRead,
    InterventionPage,
    InterventionRead,
    InterventionResolve,
    InterventionTransition,
)
from app.modules.interventions.service import (
    assign_intervention,
    assign_intervention_action,
    cancel_intervention,
    close_intervention,
    complete_intervention_action,
    create_intervention,
    create_intervention_action,
    create_intervention_followup,
    get_intervention,
    get_intervention_action,
    get_intervention_followup,
    list_intervention_actions,
    list_intervention_followups,
    list_student_interventions,
    resolve_intervention,
    transition_intervention,
    transition_intervention_action,
)

router = APIRouter(prefix="/interventions", tags=["interventions"])

SessionDep = Annotated[Session, Depends(get_session)]
ReadPrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_read)]
CreatePrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_create)]
UpdatePrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_update)]
AssignPrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_assign)]
ResolvePrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_resolve)]
ClosePrincipalDep = Annotated[CurrentPrincipal, Depends(require_intervention_close)]
ActionManagePrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_intervention_action_manage),
]
FollowUpCreatePrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(require_intervention_followup_create),
]


@router.post("", response_model=InterventionRead, status_code=status.HTTP_201_CREATED)
def create_intervention_api(
    payload: InterventionCreate,
    principal: CreatePrincipalDep,
    session: SessionDep,
):
    return create_intervention(session, principal, payload)


@router.get("/{intervention_id}", response_model=InterventionRead)
def get_intervention_api(
    intervention_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
):
    return get_intervention(session, principal, intervention_id)


@router.get("/students/{student_profile_id}", response_model=InterventionPage)
def list_student_interventions_api(
    student_profile_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(OPEN|IN_PROGRESS|MONITORING|RESOLVED|CLOSED|CANCELLED)$",
    ),
    sensitivity_filter: str | None = Query(
        default=None,
        alias="sensitivity",
        pattern="^(GENERAL|RESTRICTED|CONFIDENTIAL)$",
    ),
):
    items = list_student_interventions(
        session,
        principal,
        student_profile_id=student_profile_id,
        limit=limit,
        status_filter=status_filter,
        sensitivity_filter=sensitivity_filter,
    )
    return InterventionPage(items=items, count=len(items))


@router.post("/{intervention_id}/assign", response_model=InterventionRead)
def assign_intervention_api(
    intervention_id: UUID,
    payload: InterventionAssign,
    principal: AssignPrincipalDep,
    session: SessionDep,
):
    return assign_intervention(session, principal, intervention_id, payload)


@router.post("/{intervention_id}/transition", response_model=InterventionRead)
def transition_intervention_api(
    intervention_id: UUID,
    payload: InterventionTransition,
    principal: UpdatePrincipalDep,
    session: SessionDep,
):
    return transition_intervention(session, principal, intervention_id, payload)


@router.post("/{intervention_id}/resolve", response_model=InterventionRead)
def resolve_intervention_api(
    intervention_id: UUID,
    payload: InterventionResolve,
    principal: ResolvePrincipalDep,
    session: SessionDep,
):
    return resolve_intervention(session, principal, intervention_id, payload)


@router.post("/{intervention_id}/close", response_model=InterventionRead)
def close_intervention_api(
    intervention_id: UUID,
    payload: InterventionClose,
    principal: ClosePrincipalDep,
    session: SessionDep,
):
    return close_intervention(session, principal, intervention_id, payload)


@router.post("/{intervention_id}/cancel", response_model=InterventionRead)
def cancel_intervention_api(
    intervention_id: UUID,
    payload: InterventionCancel,
    principal: UpdatePrincipalDep,
    session: SessionDep,
):
    return cancel_intervention(session, principal, intervention_id, payload)

@router.post(
    "/{intervention_id}/actions",
    response_model=InterventionActionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_intervention_action_api(
    intervention_id: UUID,
    payload: InterventionActionCreate,
    principal: ActionManagePrincipalDep,
    session: SessionDep,
):
    return create_intervention_action(
        session,
        principal,
        intervention_id,
        payload,
    )


@router.get(
    "/{intervention_id}/actions",
    response_model=InterventionActionPage,
)
def list_intervention_actions_api(
    intervention_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=(
            "^(OPEN|ACKNOWLEDGED|IN_PROGRESS|COMPLETED|"
            "CANCELLED|OVERDUE)$"
        ),
    ),
):
    items = list_intervention_actions(
        session,
        principal,
        intervention_id=intervention_id,
        limit=limit,
        status_filter=status_filter,
    )
    return InterventionActionPage(items=items, count=len(items))


@router.get(
    "/actions/{action_id}",
    response_model=InterventionActionRead,
)
def get_intervention_action_api(
    action_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
):
    return get_intervention_action(session, principal, action_id)


@router.post(
    "/actions/{action_id}/assign",
    response_model=InterventionActionRead,
)
def assign_intervention_action_api(
    action_id: UUID,
    payload: InterventionActionAssign,
    principal: ActionManagePrincipalDep,
    session: SessionDep,
):
    return assign_intervention_action(
        session,
        principal,
        action_id,
        payload,
    )


@router.post(
    "/actions/{action_id}/transition",
    response_model=InterventionActionRead,
)
def transition_intervention_action_api(
    action_id: UUID,
    payload: InterventionActionTransition,
    principal: ActionManagePrincipalDep,
    session: SessionDep,
):
    return transition_intervention_action(
        session,
        principal,
        action_id,
        payload,
    )


@router.post(
    "/actions/{action_id}/complete",
    response_model=InterventionActionRead,
)
def complete_intervention_action_api(
    action_id: UUID,
    payload: InterventionActionComplete,
    principal: ActionManagePrincipalDep,
    session: SessionDep,
):
    return complete_intervention_action(
        session,
        principal,
        action_id,
        payload,
    )


@router.post(
    "/{intervention_id}/followups",
    response_model=InterventionFollowUpRead,
    status_code=status.HTTP_201_CREATED,
)
def create_intervention_followup_api(
    intervention_id: UUID,
    payload: InterventionFollowUpCreate,
    principal: FollowUpCreatePrincipalDep,
    session: SessionDep,
):
    return create_intervention_followup(
        session,
        principal,
        intervention_id,
        payload,
    )


@router.get(
    "/{intervention_id}/followups",
    response_model=InterventionFollowUpPage,
)
def list_intervention_followups_api(
    intervention_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=100),
    sensitivity_filter: str | None = Query(
        default=None,
        alias="sensitivity",
        pattern="^(GENERAL|RESTRICTED|CONFIDENTIAL)$",
    ),
):
    items = list_intervention_followups(
        session,
        principal,
        intervention_id=intervention_id,
        limit=limit,
        sensitivity_filter=sensitivity_filter,
    )
    return InterventionFollowUpPage(items=items, count=len(items))


@router.get(
    "/followups/{followup_id}",
    response_model=InterventionFollowUpRead,
)
def get_intervention_followup_api(
    followup_id: UUID,
    principal: ReadPrincipalDep,
    session: SessionDep,
):
    return get_intervention_followup(
        session,
        principal,
        followup_id,
    )
