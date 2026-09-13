from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class StudentTimelineEntry(SQLModel, table=True):
    __tablename__ = "student_timeline_entries"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "ledger_event_id",
            name="uq_student_timeline_inst_ledger_event",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    ledger_event_id: UUID
    ledger_position: int = Field(sa_column=Column(BigInteger, nullable=False))
    event_type: str = Field(max_length=180)
    event_version: int = Field(default=1, ge=1)
    category: str = Field(max_length=32)
    importance: str = Field(default="NORMAL", max_length=20)
    sensitivity: str = Field(default="GENERAL", max_length=20)
    title: str = Field(max_length=180)
    summary: str | None = Field(default=None, max_length=1200)
    source_aggregate_type: str = Field(max_length=100)
    source_aggregate_id: UUID
    actor_user_id: UUID | None = None
    correlation_id: UUID | None = Field(default=None, index=True)
    causation_id: UUID | None = None
    context_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    occurred_at: datetime = Field(index=True)
    recorded_at: datetime
    projected_at: datetime = Field(default_factory=utcnow)
