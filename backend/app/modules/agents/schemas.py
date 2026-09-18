from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_run_id: UUID


class StudentTimelineAgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: UUID


class InstitutionIntelligenceAgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntegrationRunExplainerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration_run_id: UUID
    explanation_focus: Literal["SUMMARY", "ERRORS", "OUTCOME"]


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


class ProviderFindingRead(BaseModel):
    text: str = Field(min_length=1, max_length=700)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)


class IntegrationRunExplainerOutput(BaseModel):
    agent_key: str = "integration_run_explainer"
    run_id: UUID
    explanation_focus: Literal["SUMMARY", "ERRORS", "OUTCOME"]
    explanation_mode: Literal["DETERMINISTIC_FALLBACK", "FAKE_PROVIDER"]
    provider_failure_code: str | None = None
    evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=1, max_length=1_200)
    key_findings: list[ProviderFindingRead] = Field(max_length=8)
    caveats: list[str] = Field(max_length=8)
    evidence_refs: list[AgentEvidenceRead]


class StudentTimelineSummaryRead(BaseModel):
    event_count: int = Field(ge=0)
    recent_event_types: list[str] = Field(max_length=20)
    latest_event_at: datetime | None = None


class InterventionSummaryRead(BaseModel):
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    in_progress: int = Field(ge=0)
    closed: int = Field(ge=0)


class FollowupSummaryRead(BaseModel):
    total: int = Field(ge=0)
    latest_at: datetime | None = None


class StudentTimelineAdvisorOutput(BaseModel):
    agent_key: str = "student_timeline_advisor"
    student_id: UUID
    summary: str = Field(max_length=500)
    timeline: StudentTimelineSummaryRead
    interventions: InterventionSummaryRead
    followups: FollowupSummaryRead
    issues: list[AgentIssueRead]
    safe_next_action: str = Field(max_length=500)
    evidence_refs: list[AgentEvidenceRead]


class IntelligenceSignalSummaryRead(BaseModel):
    total: int = Field(ge=0)
    low: int = Field(ge=0)
    medium: int = Field(ge=0)
    high: int = Field(ge=0)


class IntelligenceProvenanceRead(BaseModel):
    policy_key: str
    policy_version: int = Field(ge=1)
    generated_at: datetime


class InstitutionIntelligenceAdvisorOutput(BaseModel):
    agent_key: str = "institution_intelligence_advisor"
    snapshot_id: UUID
    snapshot_date: date
    freshness: str
    summary: str = Field(max_length=500)
    signals: IntelligenceSignalSummaryRead
    top_categories: list[str] = Field(max_length=10)
    provenance: IntelligenceProvenanceRead
    safe_next_action: str = Field(max_length=500)
    evidence_refs: list[AgentEvidenceRead]


AgentAdvisorOutput = (
    IntegrationRunAdvisorOutput
    | IntegrationRunExplainerOutput
    | StudentTimelineAdvisorOutput
    | InstitutionIntelligenceAdvisorOutput
)


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
    output: AgentAdvisorOutput | None = None


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
