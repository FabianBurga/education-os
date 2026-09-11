from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class PilotReadinessRun(SQLModel, table=True):
    __tablename__ = "pilot_readiness_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    executed_by_user_id: UUID | None = Field(default=None, index=True)
    status: str = Field(max_length=20)
    checks_total: int
    checks_passed: int
    checks_failed: int
    report_json: str
    executed_at: datetime = Field(default_factory=utcnow)
