from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
