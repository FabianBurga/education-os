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
    provider_policy: str = Field(max_length=64)
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


class AgentModelRegistry(SQLModel, table=True):
    """Immutable, tenant-scoped provider/model configuration.

    Credentials deliberately remain outside the database.  A later governed
    router may only select rows that are enabled and policy eligible.
    """

    __tablename__ = "agent_model_registry"
    __table_args__ = (
        UniqueConstraint(
            "institution_id", "provider_key", "model_key", "version",
            name="uq_agent_model_registry_version",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    provider_key: str = Field(max_length=40, index=True)
    model_key: str = Field(max_length=120, index=True)
    version: int = Field(ge=1)
    status: str = Field(max_length=20, index=True)
    capability_class: str = Field(max_length=40)
    routing_priority: int = Field(ge=1)
    context_limit: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_estimated_cost_microusd: int = Field(ge=0)
    timeout_seconds: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    max_fallbacks: int = Field(ge=0)
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentProviderCall(SQLModel, table=True):
    """Append-only, hash-only provider execution audit; never raw prompts."""

    __tablename__ = "agent_provider_calls"
    __table_args__ = (UniqueConstraint("agent_run_id", "attempt_number", name="uq_agent_provider_calls_attempt"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    agent_run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    model_registry_id: UUID = Field(foreign_key="agent_model_registry.id", index=True)
    attempt_number: int = Field(ge=1)
    provider_key: str = Field(max_length=40)
    model_key: str = Field(max_length=120)
    model_version: int = Field(ge=1)
    evidence_manifest_sha256: str = Field(max_length=64)
    prompt_contract_sha256: str = Field(max_length=64)
    request_sha256: str = Field(max_length=64)
    response_sha256: str | None = Field(default=None, max_length=64)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_microusd: int = Field(ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    normalized_outcome: str = Field(max_length=30)
    normalized_error_code: str | None = Field(default=None, max_length=60)
    fallback_parent_call_id: UUID | None = Field(default=None, foreign_key="agent_provider_calls.id", index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AgentBudgetEvent(SQLModel, table=True):
    """Append-only reservation ledger for future provider budget admission."""

    __tablename__ = "agent_budget_events"
    __table_args__ = (UniqueConstraint("institution_id", "idempotency_key", name="uq_agent_budget_events_idempotency"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    agent_run_id: UUID = Field(foreign_key="agent_runs.id", index=True)
    provider_call_id: UUID | None = Field(default=None, foreign_key="agent_provider_calls.id", index=True)
    agent_key: str = Field(max_length=120, index=True)
    provider_key: str | None = Field(default=None, max_length=40)
    model_key: str | None = Field(default=None, max_length=120)
    event_type: str = Field(max_length=20)
    budget_scope: str = Field(max_length=20)
    period_start: datetime = Field(index=True)
    amount_microusd: int = Field(ge=0)
    idempotency_key: str = Field(max_length=160)
    correlation_id: UUID = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
