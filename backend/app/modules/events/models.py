from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    institution_id: UUID = Field(foreign_key="institutions.id", index=True)
    event_type: str = Field(max_length=180, index=True)
    aggregate_type: str = Field(max_length=100)
    aggregate_id: UUID
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="PENDING", max_length=30, index=True)
    attempts: int = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)
    processed_at: datetime | None = None
