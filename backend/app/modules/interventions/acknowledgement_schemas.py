from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AcknowledgementEvidenceLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: UUID
    idempotency_key: UUID


class AcknowledgementEvidenceCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: UUID
    reason_code: Literal["WRONG_CONTEXT", "DUPLICATE_ASSOCIATION", "ACKNOWLEDGEMENT_NOT_RELEVANT"]
    replacement_followup_id: UUID | None = None
    idempotency_key: UUID


class AcknowledgementEvidenceMutationRead(BaseModel):
    id: UUID


class AcknowledgementEvidenceRead(BaseModel):
    link_id: UUID
    receipt_id: UUID
    target_id: UUID
    generation: int
    linked_at: object
    effective_state: Literal["ACTIVE", "VOIDED", "SUPERSEDED"]
    reason_code: str | None
