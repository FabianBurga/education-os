from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StudentTimelineEntryRead(BaseModel):
    id: UUID
    student_profile_id: UUID
    ledger_event_id: UUID
    ledger_position: int
    event_type: str
    event_version: int
    category: str
    importance: str
    sensitivity: str
    title: str
    summary: str | None
    source_aggregate_type: str
    source_aggregate_id: UUID
    actor_user_id: UUID | None
    correlation_id: UUID | None
    causation_id: UUID | None
    context_json: dict
    occurred_at: datetime
    recorded_at: datetime
    projected_at: datetime


class StudentTimelinePage(BaseModel):
    student_profile_id: UUID
    entries: list[StudentTimelineEntryRead] = Field(default_factory=list)
    next_before_position: int | None = None