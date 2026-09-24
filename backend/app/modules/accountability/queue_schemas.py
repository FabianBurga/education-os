from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AccountabilityQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: UUID
    identity_version: int
    identity_key_sha256: str
    source_category: str
    normalized_category: str
    attention_reasons: tuple[str, ...]
    owner_state: str
    owner_user_id: UUID | None
    review_required: bool
    decision_required: bool
    open_obligation_id: UUID | None
    open_obligation_type: str | None
    next_required_step: str
    due_at: datetime | None
    sla_status: str
    compliance_status: str
    m22_priority: str | None
    m22_snapshot_id: UUID | None
    case_age_seconds: int
    generated_at: datetime
    source_freshness: datetime | None
    projection_version: int
    policy_versions: tuple[str, ...]
    provenance_refs: tuple[str, ...]


class AccountabilityQueuePageRead(BaseModel):
    items: tuple[AccountabilityQueueItemRead, ...]
    next_cursor: str | None
    generated_at: datetime


class AccountabilityCaseDetailRead(BaseModel):
    item: AccountabilityQueueItemRead
    source_lineage: tuple[dict[str, Any], ...]
    ownership_history: tuple[dict[str, Any], ...]
    reviews: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    obligations: tuple[dict[str, Any], ...]
    m21_links: tuple[dict[str, Any], ...]
    m22_reference: dict[str, Any] | None
    generated_at: datetime
