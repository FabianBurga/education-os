from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    institution_id: UUID = Field(foreign_key="institutions.id", index=True)
    actor_user_id: UUID | None = Field(default=None, foreign_key="user_accounts.id", index=True)
    action: str = Field(max_length=160, index=True)
    entity_type: str = Field(max_length=120)
    entity_id: UUID | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)
