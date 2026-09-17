from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentDefinition(SQLModel, table=True):
    __tablename__ = "agent_definitions"
    __table_args__ = (UniqueConstraint("institution_id", "agent_key", "version", name="uq_agent_definitions_version"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    agent_key: str = Field(max_length=120, index=True)
    version: int = Field(ge=1)
    status: str = Field(max_length=20, index=True)
    capability_keys_json: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    tool_keys_json: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    max_autonomy_level: str = Field(max_length=8)
    config_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentPolicyVersion(SQLModel, table=True):
    __tablename__ = "agent_policy_versions"
    __table_args__ = (UniqueConstraint("institution_id", "policy_key", "version", name="uq_agent_policy_versions_version"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    policy_key: str = Field(max_length=120, index=True)
    version: int = Field(ge=1)
    status: str = Field(max_length=20, index=True)
    max_autonomy_level: str = Field(max_length=8)
    max_steps: int = Field(ge=1)
    max_tool_calls: int = Field(ge=1)
    provider_policy: str = Field(max_length=40)
    config_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("institution_id", "agent_key", "request_sha256", name="uq_agent_runs_request"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    actor_user_id: UUID = Field(index=True)
    agent_key: str = Field(max_length=120, index=True)
    agent_definition_id: UUID = Field(foreign_key="agent_definitions.id", index=True)
    agent_definition_version: int = Field(ge=1)
    policy_id: UUID = Field(foreign_key="agent_policy_versions.id", index=True)
    policy_version: int = Field(ge=1)
    request_type: str = Field(max_length=80)
    request_sha256: str = Field(max_length=64)
    correlation_id: UUID = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentRunStep(SQLModel, table=True):
    __tablename__ = "agent_run_steps"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_agent_run_steps_sequence"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    sequence: int = Field(ge=1)
    step_type: str = Field(max_length=40)
    status: str = Field(max_length=20)
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentToolCall(SQLModel, table=True):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_agent_tool_calls_sequence"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    sequence: int = Field(ge=1)
    tool_key: str = Field(max_length=160)
    schema_version: str = Field(max_length=40)
    input_sha256: str = Field(max_length=64)
    output_sha256: str = Field(max_length=64)
    verification_status: str = Field(max_length=20)
    safe_summary_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentEvidenceRef(SQLModel, table=True):
    __tablename__ = "agent_evidence_refs"
    __table_args__ = (UniqueConstraint("run_id", "reference_key", name="uq_agent_evidence_refs_reference"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    reference_key: str = Field(max_length=220)
    source_module: str = Field(max_length=80)
    source_entity_type: str = Field(max_length=120)
    source_entity_id: UUID = Field(index=True)
    provenance_sha256: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentRunEvent(SQLModel, table=True):
    __tablename__ = "agent_run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_sequence"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    sequence: int = Field(ge=1)
    event_type: str = Field(max_length=30)
    actor_user_id: UUID | None = Field(default=None, index=True)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, index=True)
