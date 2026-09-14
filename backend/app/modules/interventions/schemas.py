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


class InterventionRead(BaseModel):
    id: UUID
    organization_id: UUID
    institution_id: UUID
    student_profile_id: UUID
    academic_period_id: UUID | None = None
    section_id: UUID | None = None
    intervention_type: str
    severity: str
    status: str
    sensitivity: str
    title: str
    reason: str | None = None
    objective: str | None = None
    origin_type: str
    opened_by_user_id: UUID
    assigned_role_code: str | None = None
    assigned_user_id: UUID | None = None
    opened_at: datetime
    target_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    outcome_type: str | None = None
    outcome_summary: str | None = None
    outcome_recorded_at: datetime | None = None
    outcome_recorded_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    protected_detail: bool = False

    model_config = {"from_attributes": True}


class InterventionPage(BaseModel):
    items: list[InterventionRead]
    count: int



class InterventionActionCreate(BaseModel):
    action_type: str = Field(default="REVIEW", min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=2000)
    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None


class InterventionActionAssign(BaseModel):
    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def assignment_target_present(self):
        if self.assigned_role_code is None and self.assigned_user_id is None:
            raise ValueError(
                "assigned_role_code or assigned_user_id is required"
            )
        return self


class InterventionActionTransition(BaseModel):
    status: str = Field(pattern="^(ACKNOWLEDGED|IN_PROGRESS|CANCELLED)$")


class InterventionActionComplete(BaseModel):
    completion_note: str | None = Field(default=None, max_length=2000)


class InterventionFollowUpCreate(BaseModel):
    followup_type: str = Field(
        pattern=(
            "^(MEETING|PHONE_CALL|FAMILY_CONTACT|STUDENT_CONVERSATION|"
            "TEACHER_REVIEW|ACADEMIC_REVIEW|ATTENDANCE_REVIEW|"
            "PSYCHOLOGY_SESSION|REFERRAL|OTHER)$"
        )
    )
    sensitivity: str = Field(
        default="GENERAL",
        pattern="^(GENERAL|RESTRICTED|CONFIDENTIAL)$",
    )
    note: str = Field(min_length=1, max_length=4000)
    observed_at: datetime

class InterventionActionRead(BaseModel):
    id: UUID
    organization_id: UUID
    institution_id: UUID
    intervention_id: UUID
    action_type: str
    title: str
    description: str | None = None
    status: str
    assigned_role_code: str | None = None
    assigned_user_id: UUID | None = None
    due_at: datetime | None = None
    acknowledged_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    completion_note: str | None = None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    protected_detail: bool = False

    model_config = {"from_attributes": True}


class InterventionActionPage(BaseModel):
    items: list[InterventionActionRead]
    count: int


class InterventionFollowUpRead(BaseModel):
    id: UUID
    organization_id: UUID
    institution_id: UUID
    intervention_id: UUID
    followup_type: str
    sensitivity: str
    note: str | None = None
    observed_at: datetime
    created_by_user_id: UUID
    created_at: datetime
    protected_detail: bool = False

    model_config = {"from_attributes": True}


class InterventionFollowUpPage(BaseModel):
    items: list[InterventionFollowUpRead]
    count: int

class InstitutionalInterventionItem(BaseModel):
    id: UUID
    student_profile_id: UUID
    intervention_type: str
    severity: str
    status: str
    sensitivity: str
    title: str
    assigned_role_code: str | None = None
    assigned_user_id: UUID | None = None
    target_at: datetime | None = None
    opened_at: datetime
    protected_detail: bool = True


class InstitutionalInterventionQueue(BaseModel):
    items: list[InstitutionalInterventionItem]
    count: int
    status_counts: dict[str, int]
    overdue_count: int
    unassigned_count: int
