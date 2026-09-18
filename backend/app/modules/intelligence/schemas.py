from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PriorityValue = Literal["LOW", "MEDIUM", "HIGH"]
PolicySourceValue = Literal["BUILTIN_DEFAULT", "CONTROL_PLANE"]
CohortTypeValue = Literal[
    "INSTITUTION",
    "ACADEMIC_LEVEL",
    "GRADE",
    "SECTION",
    "COURSE",
]


class RectorOverview(BaseModel):
    active_students: int
    active_sections: int
    attendance_rate: float | None
    absence_rate: float | None
    late_rate: float | None
    academic_average_percent: float | None
    missing_grade_entries: int
    open_signals: int


class SectionIntelligence(BaseModel):
    section_id: UUID
    section_name: str
    grade_name: str
    student_count: int
    attendance_rate: float | None
    academic_average_percent: float | None
    open_signals: int


class AttendanceTrendPoint(BaseModel):
    day: date
    total_records: int
    attendance_rate: float | None
    absence_rate: float | None
    late_rate: float | None


class AcademicTrendPoint(BaseModel):
    grading_period_id: UUID
    grading_period_name: str
    average_percent: float | None
    graded_entries: int
    missing_entries: int


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    institution_id: UUID
    academic_period_id: UUID | None
    section_id: UUID | None
    student_profile_id: UUID
    signal_type: str
    severity: str
    metric_value: float
    threshold_value: float
    summary: str
    status: str
    detected_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class SignalResolve(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=1000)


class SignalRefreshResult(BaseModel):
    detected_or_refreshed: int
    auto_closed: int


class IntelligenceOverviewRead(BaseModel):
    academic_period_id: UUID | None
    snapshot_date: date
    in_scope_student_count: int
    high_priority_count: int
    medium_priority_count: int
    active_intervention_count: int
    interventions_without_action_count: int
    overdue_followup_count: int
    positive_outcome_count: int
    unresolved_outcome_count: int
    attendance_risk_count: int | None
    academic_risk_count: int | None
    rule_set_version: int
    projection_version: int
    policy_source: PolicySourceValue
    policy_key: str
    policy_version: int
    control_revision: int | None


class IntelligencePriorityItem(BaseModel):
    student_profile_id: UUID
    academic_period_id: UUID | None
    snapshot_date: date
    overall_priority: PriorityValue
    attendance_priority: PriorityValue
    academic_priority: PriorityValue
    intervention_priority: PriorityValue
    evidence_count: int
    rule_set_version: int
    projection_version: int
    policy_source: PolicySourceValue
    policy_version: int
    control_revision: int | None


class CohortIntelligenceRead(BaseModel):
    academic_period_id: UUID | None
    snapshot_date: date
    cohort_type: CohortTypeValue
    cohort_ref_id: UUID | None
    student_count: int
    high_priority_count: int | None
    medium_priority_count: int | None
    attendance_risk_count: int | None
    academic_risk_count: int | None
    active_intervention_count: int | None
    overdue_followup_count: int | None
    suppressed: bool
    rule_set_version: int
    projection_version: int
    policy_source: PolicySourceValue
    policy_version: int
    control_revision: int | None


class IntelligenceTrendPoint(BaseModel):
    snapshot_date: date
    in_scope_student_count: int
    high_priority_count: int
    medium_priority_count: int
    attendance_risk_count: int | None
    academic_risk_count: int | None
    active_intervention_count: int
    overdue_followup_count: int
    positive_outcome_count: int
    unresolved_outcome_count: int


class InterventionHealthRead(BaseModel):
    academic_period_id: UUID | None
    snapshot_date: date
    active_interventions: int
    interventions_without_action: int
    followup_overdue: int
    positive_outcomes: int
    unresolved_outcomes: int
    policy_source: PolicySourceValue
    policy_version: int
    control_revision: int | None


class InstitutionIntelligenceAgentRead(BaseModel):
    """Minimized, permission-gated M22 read boundary for M25 L0 advisors."""

    snapshot_id: UUID
    snapshot_date: date
    generated_at: datetime
    policy_key: str
    policy_version: int
    rule_set_version: int
    projection_version: int
    open_signal_total: int
    open_signal_low: int
    open_signal_medium: int
    open_signal_high: int
    top_signal_categories: list[str]
