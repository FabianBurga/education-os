from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, Column, Sequence, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


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


class EventLedger(SQLModel, table=True):
    __tablename__ = "event_ledger"
    __table_args__ = (
        UniqueConstraint(
            "source_outbox_event_id",
            name="uq_event_ledger_source_outbox",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    position: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            Sequence("event_ledger_position_seq"),
            nullable=False,
            unique=True,
        ),
    )
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    source_kind: str = Field(default="TRANSACTIONAL_OUTBOX", max_length=40)
    source_outbox_event_id: UUID
    event_type: str = Field(max_length=180, index=True)
    event_version: int = Field(default=1, ge=1)
    aggregate_type: str = Field(max_length=100, index=True)
    aggregate_id: UUID = Field(index=True)
    actor_user_id: UUID | None = None
    correlation_id: UUID | None = Field(default=None, index=True)
    causation_id: UUID | None = None
    payload_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    occurred_at: datetime = Field(index=True)
    recorded_at: datetime = Field(default_factory=utcnow, index=True)


class ProjectionCheckpoint(SQLModel, table=True):
    __tablename__ = "projection_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "projection_key",
            name="uq_projection_checkpoint_inst_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    projection_key: str = Field(max_length=120, index=True)
    last_position: int = Field(default=0)
    processed_count: int = Field(default=0)
    updated_at: datetime = Field(default_factory=utcnow)


class InstitutionEventDaily(SQLModel, table=True):
    __tablename__ = "institution_event_daily"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "event_date",
            "event_type",
            "event_version",
            name="uq_inst_event_daily_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    event_date: date = Field(index=True)
    event_type: str = Field(max_length=180, index=True)
    event_version: int = Field(default=1)
    event_count: int = Field(default=0)
    first_event_at: datetime
    last_event_at: datetime
    projection_updated_at: datetime = Field(default_factory=utcnow)


class AggregateActivitySnapshot(SQLModel, table=True):
    __tablename__ = "aggregate_activity_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "aggregate_type",
            "aggregate_id",
            name="uq_aggregate_activity_inst_aggregate",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    aggregate_type: str = Field(max_length=100, index=True)
    aggregate_id: UUID = Field(index=True)
    first_position: int
    last_position: int
    first_event_at: datetime
    last_event_at: datetime
    event_count: int = Field(default=0)
    last_event_type: str = Field(max_length=180)
    last_event_version: int = Field(default=1)
    projection_updated_at: datetime = Field(default_factory=utcnow)
