from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID


class AutomationRuleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    signal_type: str = Field(pattern="^(ATTENDANCE_RISK|REPEATED_LATE|ACADEMIC_RISK|MISSING_WORK)$")
    minimum_severity: str = Field(
        default="MEDIUM",
        pattern="^(LOW|MEDIUM|HIGH)$",
    )
    assignee_role_code: str = Field(min_length=1, max_length=60)
    task_title: str = Field(min_length=1, max_length=200)
    due_in_hours: int = Field(default=24, ge=1, le=720)
    escalate_after_hours: int = Field(default=48, ge=1, le=1440)
    is_enabled: bool = True


class AutomationRuleRead(TenantRead):
    code: str
    name: str
    signal_type: str
    minimum_severity: str
    assignee_role_code: str
    task_title: str
    due_in_hours: int
    escalate_after_hours: int
    is_enabled: bool


class AutomationCaseRead(TenantRead):
    intelligence_signal_id: UUID
    automation_rule_id: UUID
    student_profile_id: UUID
    section_id: UUID | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    outcome_note: str | None


class AutomationTaskRead(TenantRead):
    automation_case_id: UUID
    assigned_role_code: str
    task_type: str
    title: str
    description: str | None
    status: str
    due_at: datetime
    escalate_at: datetime
    acknowledged_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None


class TimelineEventRead(TenantRead):
    automation_case_id: UUID
    automation_task_id: UUID | None
    event_type: str
    message: str
    actor_user_id: UUID | None
    created_at: datetime


class TaskComplete(BaseModel):
    completion_note: str = Field(min_length=3, max_length=1000)


class EngineRunResult(BaseModel):
    signals_scanned: int
    matched_pairs: int
    cases_created: int
    tasks_created: int


class EngineTickResult(BaseModel):
    tasks_escalated: int


class BootstrapRulesResult(BaseModel):
    created: int
    existing: int
