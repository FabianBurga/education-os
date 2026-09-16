from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class IntegrationConnector(SQLModel, table=True):
    __tablename__ = "integration_connectors"
    __table_args__ = (
        UniqueConstraint("institution_id", "connector_key", name="uq_integration_connectors_key"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    connector_key: str = Field(max_length=120, index=True)
    connector_type: str = Field(max_length=40)
    display_name: str = Field(max_length=160)
    status: str = Field(default="ENABLED", max_length=20, index=True)
    config_version: int = Field(default=1, ge=1)
    configuration_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_by_user_id: UUID = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class IntegrationMapping(SQLModel, table=True):
    __tablename__ = "integration_mappings"
    __table_args__ = (
        UniqueConstraint("connector_id", "mapping_key", "version", name="uq_integration_mappings_version"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    connector_id: UUID = Field(foreign_key="integration_connectors.id", index=True)
    mapping_key: str = Field(max_length=120)
    version: int = Field(ge=1)
    schema_version: str = Field(max_length=80)
    mapping_sha256: str = Field(max_length=64)
    mapping_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_by_user_id: UUID = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class IntegrationRun(SQLModel, table=True):
    __tablename__ = "integration_runs"
    __table_args__ = (
        UniqueConstraint("institution_id", "connector_id", "idempotency_key", name="uq_integration_runs_idempotency"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    connector_id: UUID = Field(foreign_key="integration_connectors.id", index=True)
    mapping_id: UUID | None = Field(default=None, foreign_key="integration_mappings.id", index=True)
    initiated_by_user_id: UUID = Field(index=True)
    source_kind: str = Field(max_length=32)
    mode: str = Field(max_length=20)
    source_fingerprint_sha256: str = Field(max_length=64)
    idempotency_key: str = Field(max_length=64)
    connector_config_version: int = Field(ge=1)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class IntegrationRunEvent(SQLModel, table=True):
    __tablename__ = "integration_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_integration_run_events_sequence"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="integration_runs.id", index=True)
    run_item_id: UUID | None = Field(default=None, foreign_key="integration_run_items.id", index=True)
    sequence: int = Field(ge=1)
    event_type: str = Field(max_length=20)
    actor_user_id: UUID | None = Field(default=None, index=True)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class IntegrationRunItem(SQLModel, table=True):
    __tablename__ = "integration_run_items"
    __table_args__ = (
        UniqueConstraint("run_id", "source_item_key", name="uq_integration_run_items_source_key"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="integration_runs.id", index=True)
    source_item_key: str = Field(max_length=180)
    source_item_fingerprint_sha256: str = Field(max_length=64)
    canonical_entity_type: str = Field(max_length=80)
    operation_class: str = Field(max_length=40)
    status: str = Field(max_length=20, index=True)
    result_entity_id: UUID | None = Field(default=None, index=True)
    error_code: str | None = Field(default=None, max_length=80)
    detail_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class IntegrationExternalStudentRef(SQLModel, table=True):
    """Immutable connector-qualified external identity for create-only student imports."""

    __tablename__ = "integration_external_student_refs"
    __table_args__ = (
        UniqueConstraint(
            "institution_id", "connector_id", "external_student_id",
            name="uq_integration_external_student_refs_identity",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    connector_id: UUID = Field(foreign_key="integration_connectors.id", index=True)
    external_student_id: str = Field(max_length=120, index=True)
    student_profile_id: UUID = Field(foreign_key="student_profiles.id", index=True)
    created_run_id: UUID = Field(foreign_key="integration_runs.id", index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
