from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.copilot.advisory import generate_advisory_answer
from app.modules.copilot.api_schemas import (
    CopilotQueryRequest,
    CopilotQueryResponse,
    CopilotRunResponse,
)
from app.modules.copilot.api_service import get_visible_copilot_run

router = APIRouter(
    prefix="/copilot",
    tags=["copilot"],
)

PrincipalDep = Annotated[
    CurrentPrincipal,
    Depends(get_current_principal),
]
SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/queries",
    response_model=CopilotQueryResponse,
)
def create_copilot_query(
    payload: CopilotQueryRequest,
    principal: PrincipalDep,
    session: SessionDep,
) -> CopilotQueryResponse:
    execution = generate_advisory_answer(
        session,
        principal,
        intent=payload.intent,
        request_text=payload.request_text,
        target_student_profile_id=payload.target_student_profile_id,
    )
    session.commit()

    return CopilotQueryResponse(
        run_id=execution.run_id,
        status=execution.status,
        answer=execution.answer,
        citations=list(execution.citations),
        evidence_assessment=execution.evidence_assessment,
        failure_code=execution.failure_code,
    )


@router.get(
    "/runs/{run_id}",
    response_model=CopilotRunResponse,
)
def read_copilot_run(
    run_id: UUID,
    principal: PrincipalDep,
    session: SessionDep,
) -> CopilotRunResponse:
    run = get_visible_copilot_run(
        session,
        principal,
        run_id=run_id,
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Copilot run not found",
        )
    return run
