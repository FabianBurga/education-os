from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class IntelligenceSignal(SQLModel, table=True):
    __tablename__ = "intelligence_signals"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id",
            "academic_period_id",
            "signal_type",
            "status",
            name="uq_intelligence_signal_student_period_type_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    section_id: UUID | None = Field(default=None, index=True)
    student_profile_id: UUID = Field(index=True)
    signal_type: str = Field(max_length=40)
    severity: str = Field(max_length=20)
    metric_value: float
    threshold_value: float
    summary: str = Field(max_length=500)
    status: str = Field(default="OPEN", max_length=20)
    detected_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    resolution_note: str | None = Field(default=None, max_length=1000)
