from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class CopilotPolicyVersion(SQLModel, table=True):
    __tablename__ = "copilot_policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "policy_key",
            "version",
            name="uq_copilot_policy_version",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    policy_key: str = Field(max_length=120, index=True)
    version: int = Field(ge=1)
    status: str = Field(max_length=20, index=True)
    max_daily_runs_per_user: int = Field(default=50, ge=1)
    max_evidence_items: int = Field(default=30, ge=1, le=100)
    allow_action_proposals: bool = False
    config_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CopilotPromptVersion(SQLModel, table=True):
    __tablename__ = "copilot_prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "prompt_key",
            "version",
            name="uq_copilot_prompt_version",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    prompt_key: str = Field(max_length=120, index=True)
    version: int = Field(ge=1)
    intent: str = Field(max_length=80, index=True)
    output_schema_version: str = Field(max_length=80)
    policy_key: str = Field(max_length=120)
    policy_version: int = Field(ge=1)
    status: str = Field(max_length=20, index=True)
    template_text: str = Field(sa_column=Column(Text, nullable=False))
    template_sha256: str = Field(max_length=64)
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CopilotModelRegistry(SQLModel, table=True):
    __tablename__ = "copilot_model_registry"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "provider_key",
            "model_key",
            "config_version",
            name="uq_copilot_model_registry_version",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    provider_key: str = Field(max_length=80, index=True)
    model_key: str = Field(max_length=160, index=True)
    config_version: int = Field(default=1, ge=1)
    capability_class: str = Field(max_length=40)
    enabled: bool = False
    policy_eligible: bool = False
    max_input_tokens: int = Field(default=4096, ge=1)
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_by_user_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CopilotRun(SQLModel, table=True):
    __tablename__ = "copilot_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    actor_user_id: UUID = Field(index=True)
    intent: str = Field(max_length=80, index=True)
    status: str = Field(max_length=30, index=True)
    request_sha256: str = Field(max_length=64)
    target_student_profile_id: UUID | None = Field(default=None, index=True)
    policy_key: str | None = Field(default=None, max_length=120)
    policy_version: int | None = None
    prompt_key: str | None = Field(default=None, max_length=120)
    prompt_version: int | None = None
    provider_key: str | None = Field(default=None, max_length=80)
    model_key: str | None = Field(default=None, max_length=160)
    model_config_version: int | None = None
    evidence_manifest_sha256: str | None = Field(default=None, max_length=64)
    output_schema_version: str | None = Field(default=None, max_length=80)
    failure_code: str | None = Field(default=None, max_length=80)
    usage_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    cost_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)
    completed_at: datetime | None = None


class CopilotEvidenceRef(SQLModel, table=True):
    __tablename__ = "copilot_evidence_refs"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "reference_key",
            name="uq_copilot_evidence_run_reference",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="copilot_runs.id", index=True)
    evidence_type: str = Field(max_length=80, index=True)
    source_module: str = Field(max_length=80)
    source_entity_type: str = Field(max_length=120)
    source_entity_id: UUID | None = Field(default=None, index=True)
    reference_key: str = Field(max_length=220)
    freshness_status: str = Field(max_length=20)
    source_version: str | None = Field(default=None, max_length=160)
    evidence_sha256: str = Field(max_length=64)
    scope_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    content_json: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)

class CopilotAdvisoryOutput(SQLModel, table=True):
    __tablename__ = "copilot_advisory_outputs"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_copilot_advisory_output_run",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    run_id: UUID = Field(foreign_key="copilot_runs.id", index=True)
    status: str = Field(max_length=30)
    answer_text: str = Field(sa_column=Column(Text, nullable=False))
    citations_json: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    evidence_assessment: str = Field(max_length=20)
    limitations_json: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    response_sha256: str = Field(max_length=64)
    provider_response_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utcnow, index=True)

