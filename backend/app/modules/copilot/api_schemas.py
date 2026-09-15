from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CopilotQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    request_text: str = Field(min_length=1, max_length=6000)
    target_student_profile_id: UUID | None = None


class CopilotQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: str
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    evidence_assessment: str | None = None
    failure_code: str | None = None


class CopilotRunProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_key: str | None = None
    policy_version: int | None = None
    prompt_key: str | None = None
    prompt_version: int | None = None
    provider_key: str | None = None
    model_key: str | None = None
    model_config_version: int | None = None


class CopilotRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    intent: str
    status: str
    failure_code: str | None = None
    answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    evidence_assessment: Literal[
        "SUFFICIENT",
        "LIMITED",
        "INSUFFICIENT",
    ] | None = None
    limitations: list[str] = Field(default_factory=list)
    provenance: CopilotRunProvenance
    usage: dict[str, object] = Field(default_factory=dict)
    cost: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None
