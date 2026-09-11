from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CoordinationSummary(BaseModel):
    active_students: int
    active_sections: int
    attendance_rate: float | None
    absence_rate: float | None
    late_rate: float | None
    academic_average_percent: float | None
    missing_grade_entries: int
    open_signals: int
    high_signals: int
    open_cases: int
    open_tasks: int
    acknowledged_tasks: int
    escalated_tasks: int


class AttentionItem(BaseModel):
    signal_id: UUID
    student_profile_id: UUID
    student_name: str
    student_code: str | None
    section_id: UUID | None
    section_name: str | None
    grade_name: str | None
    signal_type: str
    severity: str
    metric_value: float
    threshold_value: float
    summary: str
    detected_at: datetime
    last_seen_at: datetime
    case_id: UUID | None
    case_status: str | None
    task_id: UUID | None
    task_title: str | None
    task_status: str | None
    assigned_role_code: str | None
    due_at: datetime | None


class CoordinationTask(BaseModel):
    id: UUID
    automation_case_id: UUID
    assigned_role_code: str
    title: str
    description: str | None
    status: str
    due_at: datetime
    escalate_at: datetime
    acknowledged_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None


class CaseWorkspaceItem(BaseModel):
    case_id: UUID
    signal_id: UUID
    student_profile_id: UUID
    student_name: str
    student_code: str | None
    section_id: UUID | None
    section_name: str | None
    grade_name: str | None
    signal_type: str
    severity: str
    signal_summary: str
    case_status: str
    opened_at: datetime
    closed_at: datetime | None
    outcome_note: str | None
    tasks: list[CoordinationTask]


class CoordinationActionResult(BaseModel):
    status: str
    detail: str
