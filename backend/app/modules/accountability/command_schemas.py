from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Hash = str


class OwnerCommand(BaseModel):
    owner_user_id: UUID | None = None
    idempotency_key: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    reason_reference: str | None = Field(default=None, max_length=240)


class ReviewCommand(BaseModel):
    disposition: Literal[
        "CONFIRMED",
        "NEEDS_INFORMATION",
        "CONTINUE_MONITORING",
        "READY_FOR_DECISION",
        "NO_CURRENT_CONCERN",
    ]
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    evidence_fingerprint_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    next_required_step: str = Field(min_length=1, max_length=100)
    idempotency_key: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    note_reference: str | None = Field(default=None, max_length=240)


class DecisionCommand(BaseModel):
    review_id: UUID
    decision_type: Literal[
        "NO_ACTION_REQUIRED",
        "MONITOR",
        "REQUEST_INFORMATION",
        "CREATE_INTERVENTION",
        "CONTINUE_INTERVENTION",
        "ESCALATE",
        "CLOSE_CASE",
    ]
    evidence_refs: list[str] = Field(min_length=1, max_length=20)
    evidence_fingerprint_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    reason_reference: str | None = Field(default=None, max_length=240)


class ObligationCompletionCommand(BaseModel):
    evidence_type: Literal["M21_FOLLOW_UP", "M21_ACTION", "M27_HUMAN_REVIEW", "M27_INFORMATION"]
    evidence_id: UUID
    evidence_fingerprint_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: datetime | None = None


class ObligationWaiverCommand(BaseModel):
    reason_code: str = Field(min_length=3, max_length=64)
    evidence_id: UUID | None = None
    idempotency_key: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_sha256: Hash = Field(pattern=r"^[0-9a-f]{64}$")
    waived_at: datetime | None = None


class AccountabilityCommandRead(BaseModel):
    command: str
    id: UUID
    case_id: UUID | None = None
    created: bool
    decision_type: str | None = None
    lifecycle: str | None = None
    owner_user_id: UUID | None = None
    review_id: UUID | None = None
    execution_required: bool | None = None
    provenance_sha256: str
