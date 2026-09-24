from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.accountability.queue_schemas import (
    AccountabilityCaseDetailRead,
    AccountabilityQueueItemRead,
    AccountabilityQueuePageRead,
)
from app.modules.accountability.queue_service import (
    get_accountability_case_detail,
    get_accountability_queue_item,
    list_accountability_queue,
)

router = APIRouter(prefix="/accountability", tags=["accountability"])
PrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/queue", response_model=AccountabilityQueuePageRead)
def queue(
    principal: PrincipalDep,
    session: SessionDep,
    owner_user_id: UUID | None = None,
    unassigned: bool = False,
    reason: str | None = None,
    lifecycle: str | None = None,
    normalized_category: str | None = None,
    priority: str | None = None,
    obligation_type: str | None = None,
    compliance_status: str | None = None,
    due_window_hours: Annotated[int | None, Query(ge=0, le=8760)] = None,
    review_required: bool | None = None,
    decision_required: bool | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AccountabilityQueuePageRead:
    return list_accountability_queue(
        session,
        principal,
        owner_user_id=owner_user_id,
        unassigned=unassigned,
        reason=reason,
        lifecycle=lifecycle,
        normalized_category=normalized_category,
        priority=priority,
        obligation_type=obligation_type,
        compliance_status=compliance_status,
        due_window_hours=due_window_hours,
        review_required=review_required,
        decision_required=decision_required,
        cursor=cursor,
        limit=limit,
    )


@router.get("/queue/items/{case_id}", response_model=AccountabilityQueueItemRead)
def queue_item(case_id: UUID, principal: PrincipalDep, session: SessionDep) -> AccountabilityQueueItemRead:
    return get_accountability_queue_item(session, principal, case_id)


@router.get("/cases/{case_id}/accountability", response_model=AccountabilityCaseDetailRead)
def case_detail(case_id: UUID, principal: PrincipalDep, session: SessionDep) -> AccountabilityCaseDetailRead:
    return get_accountability_case_detail(session, principal, case_id)
