from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ActionProposalStatus = Literal[
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "EXECUTED",
    "FAILED",
]


class ActionProposalApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class ActionProposalRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class ActionProposalRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    run_id: UUID
    action_type: Literal["CREATE_INTERVENTION"]
    target_student_profile_id: UUID
    payload: dict[str, object]
    rationale: str
    evidence_citations: list[str]
    proposed_by_user_id: UUID
    created_at: datetime
    status: ActionProposalStatus
    last_event_at: datetime
    decision_by_user_id: UUID | None = None
    decision_note: str | None = None
    result_ref: dict[str, object] | None = None
    failure_code: str | None = None
