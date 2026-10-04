from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContinuityItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_domain: str
    source_id: UUID
    student_profile_id: UUID | None = None
    kind: str
    source_state: str
    due_at: datetime | None = None
    family_acknowledgement_indicator: bool = False
    linked_at: datetime | None = None
    deep_link: str


class ContinuityWorklistRead(BaseModel):
    items: list[ContinuityItemRead]
    has_more: bool

