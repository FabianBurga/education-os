from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AutomationRule(SQLModel, table=True):
    __tablename__ = "automation_rules"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "code",
            name="uq_automation_rules_inst_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=60)
    name: str = Field(max_length=160)
    signal_type: str = Field(max_length=40)
    minimum_severity: str = Field(default="MEDIUM", max_length=20)
    assignee_role_code: str = Field(max_length=60)
    task_title: str = Field(max_length=200)
    due_in_hours: int = 24
    escalate_after_hours: int = 48
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class AutomationCase(SQLModel, table=True):
    __tablename__ = "automation_cases"
    __table_args__ = (
        UniqueConstraint(
            "intelligence_signal_id",
            "automation_rule_id",
            name="uq_automation_cases_signal_rule",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    intelligence_signal_id: UUID = Field(index=True)
    automation_rule_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    section_id: UUID | None = Field(default=None, index=True)
    status: str = Field(default="OPEN", max_length=20)
    opened_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None
    outcome_note: str | None = Field(default=None, max_length=1000)


class AutomationTask(SQLModel, table=True):
    __tablename__ = "automation_tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    automation_case_id: UUID = Field(index=True)
    assigned_role_code: str = Field(max_length=60)
    task_type: str = Field(default="REVIEW", max_length=30)
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    status: str = Field(default="OPEN", max_length=20)
    due_at: datetime
    escalate_at: datetime
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    completion_note: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)


class AutomationTimelineEvent(SQLModel, table=True):
    __tablename__ = "automation_timeline_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    automation_case_id: UUID = Field(index=True)
    automation_task_id: UUID | None = Field(default=None, index=True)
    event_type: str = Field(max_length=40)
    message: str = Field(max_length=1000)
    actor_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
