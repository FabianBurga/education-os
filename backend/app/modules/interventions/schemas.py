from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class InterventionCreate(BaseModel):
    student_profile_id: UUID
    academic_period_id: UUID | None = None
    section_id: UUID | None = None
    intervention_type: str = Field(min_length=1, max_length=60)
    severity: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    sensitivity: str = Field(
        default="GENERAL",
        pattern="^(GENERAL|RESTRICTED|CONFIDENTIAL)$",
    )
    title: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=2000)
    objective: str | None = Field(default=None, max_length=2000)
    origin_type: str = Field(
        default="HUMAN",
        pattern="^(HUMAN|SIGNAL|LEGACY_CASE|SYSTEM_SUGGESTION)$",
    )
    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = None
    target_at: datetime | None = None


class InterventionAssign(BaseModel):
    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = None
    target_at: datetime | None = None

    @model_validator(mode="after")
    def assignment_target_present(self):
        if self.assigned_role_code is None and self.assigned_user_id is None:
            raise ValueError(
                "assigned_role_code or assigned_user_id is required"
            )
        return self


class InterventionTransition(BaseModel):
    status: str = Field(pattern="^(IN_PROGRESS|MONITORING)$")


class InterventionResolve(BaseModel):
    outcome_type: str = Field(
        pattern=(
            "^(IMPROVED|STABLE|NO_CHANGE|WORSENED|REFERRED|TRANSFERRED|"
            "NOT_ASSESSABLE)$"
        )
    )
    outcome_summary: str = Field(min_length=1, max_length=2000)


class InterventionClose(BaseModel):
    outcome_type: str = Field(
        pattern=(
            "^(IMPROVED|STABLE|NO_CHANGE|WORSENED|REFERRED|TRANSFERRED|"
            "NOT_ASSESSABLE)$"
        )
    )
    outcome_summary: str = Field(min_length=1, max_length=2000)


class InterventionCancel(BaseModel):
    cancellation_reason: str = Field(min_length=1, max_length=1000)