from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MetricStatus = Literal[
    "COMPUTED", "NOT_EVALUABLE", "NOT_COMPUTABLE", "SUPPRESSED", "INSUFFICIENT_EVIDENCE"
]


class MetricPopulation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["institution", "cohort"] = "institution"
    institution_id: UUID
    cohort_id: UUID | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class MetricProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_read_models: tuple[str, ...]
    source_event_kinds: tuple[str, ...] = ()
    lineage_digest: str
    calculator: str
    exclusions: tuple[str, ...] = ()


class MetricExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_question: str
    definition: str
    numerator_definition: str
    denominator_definition: str
    exclusions: tuple[str, ...]
    status_reason: str | None = None
    metric_version: str


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_id: str
    metric_version: str
    status: MetricStatus
    value: float | None = None
    unit: Literal["seconds", "ratio", "count", "observations"]
    numerator: float | int | None = None
    denominator: int | None = None
    window_start: datetime
    window_end: datetime
    population: MetricPopulation
    filters: dict[str, Any] = Field(default_factory=dict)
    exclusions: dict[str, int] = Field(default_factory=dict)
    not_evaluable_count: int = 0
    freshness: Literal["CURRENT", "STALE", "UNKNOWN"] = "UNKNOWN"
    policy_version: int | None = None
    projection_version: int = 1
    generated_at: datetime
    provenance: MetricProvenance
    suppression_state: Literal["NONE", "SMALL_CELL", "POLICY_MISSING"] = "NONE"
    reason: str | None = None
    explanation: MetricExplanation


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: tuple[MetricResult, ...]
    generated_at: datetime


class OutcomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: MetricStatus
    window_start: datetime
    window_end: datetime
    population: MetricPopulation
    observations: dict[str, int]
    total_interventions: int
    missing_outcome_count: int
    policy_version: int | None
    freshness: Literal["CURRENT", "STALE", "UNKNOWN"]
    provenance: MetricProvenance
    reason: str | None = None
