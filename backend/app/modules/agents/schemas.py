from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_run_id: UUID


class AgentIssueRead(BaseModel):
    row_number: int | None
    code: str
    category: str
    safe_explanation: str


class AgentCountsRead(BaseModel):
    total: int = Field(ge=0)
    valid: int = Field(ge=0)
    invalid: int = Field(ge=0)
    conflicts: int = Field(ge=0)
    applied: int = Field(ge=0)
    failed: int = Field(ge=0)


class AgentProvenanceRead(BaseModel):
    connector_key: str
    sanitized_filename: str | None
    source_sha256: str


class AgentEvidenceRead(BaseModel):
    reference_key: str
    source_module: str
    source_entity_type: str
    source_entity_id: UUID
    provenance_sha256: str


class IntegrationRunAdvisorOutput(BaseModel):
    agent_key: str = "integration_run_advisor"
    run_id: UUID
    status: str
    summary: str = Field(max_length=500)
    counts: AgentCountsRead
    issues: list[AgentIssueRead]
    provenance: AgentProvenanceRead
    safe_next_action: str = Field(max_length=500)
    evidence_refs: list[AgentEvidenceRead]


class AgentDefinitionRead(BaseModel):
    agent_key: str
    maximum_autonomy: str
    capability_keys: list[str]
    tool_keys: list[str]


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    agent_key: str
    request_type: str
    status: str
    correlation_id: UUID
    created_at: datetime
    output: IntegrationRunAdvisorOutput | None = None


class AgentRunStepRead(BaseModel):
    sequence: int
    step_type: str
    status: str
    created_at: datetime


class AgentToolCallRead(BaseModel):
    sequence: int
    tool_key: str
    schema_version: str
    verification_status: str
    created_at: datetime
