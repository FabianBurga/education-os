from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from app.modules.attendance.schemas import AttendanceExpectedState


class TeacherSummary(BaseModel):
    assigned_classes: int
    assigned_sections: int
    unique_students: int
    today_sessions: int
    relevant_open_signals: int
    open_teacher_tasks: int
    escalated_teacher_tasks: int
    missing_grade_entries: int


class TeacherClassRead(BaseModel):
    course_offering_id: UUID
    academic_period_id: UUID
    academic_period_name: str
    section_id: UUID
    section_name: str
    grade_name: str
    subject_id: UUID
    subject_code: str
    subject_name: str
    assignment_role: str
    student_count: int


class TeacherRosterStudent(BaseModel):
    student_section_assignment_id: UUID
    student_profile_id: UUID
    student_code: str | None
    student_name: str
    enrollment_number: str | None


class TeacherAttendanceCode(BaseModel):
    id: UUID
    code: str
    label: str
    semantic: str
    counts_as_present: bool
    counts_as_absent: bool
    counts_as_late: bool


class TeacherSessionCreate(BaseModel):
    session_date: date
    starts_at: time
    ends_at: time
    schedule_slot_id: UUID | None = None

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class TeacherClassSession(BaseModel):
    id: UUID
    course_offering_id: UUID
    section_id: UUID
    session_date: date
    starts_at: time
    ends_at: time
    status: str


class TeacherAttendanceMark(BaseModel):
    student_section_assignment_id: UUID
    attendance_code_id: UUID
    minutes_late: int = Field(default=0, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=500)


class TeacherAttendanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_section_assignment_id: UUID
    attendance_code_id: UUID
    minutes_late: int = Field(default=0, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=500)
    expected_state: AttendanceExpectedState | None = None
    correction_reason: Literal["DATA_ENTRY_ERROR", "EVIDENCE_CORRECTION"] | None = None


class TeacherAttendanceRow(BaseModel):
    student_section_assignment_id: UUID
    student_profile_id: UUID
    student_code: str | None
    student_name: str
    attendance_record_id: UUID | None
    attendance_code_id: UUID | None
    attendance_code: str | None
    attendance_label: str | None
    minutes_late: int
    note: str | None


class TeacherGradingPeriod(BaseModel):
    id: UUID
    academic_period_id: UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    sequence: int
    status: str


class TeacherCategoryCreate(BaseModel):
    grading_period_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    weight_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class TeacherCategoryRead(BaseModel):
    id: UUID
    course_offering_id: UUID
    grading_period_id: UUID
    code: str
    name: str
    weight_percent: float


class TeacherAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grading_period_id: UUID
    assessment_category_id: UUID
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    max_score: FiniteFloat = Field(gt=0.0)
    due_on: date | None = None
    operation_id: UUID

    @model_validator(mode="after")
    def valid_max_score_precision(self):
        from decimal import Decimal

        value = Decimal(str(self.max_score))
        if value > Decimal("99999.999") or value.quantize(Decimal("0.001")) != value:
            raise ValueError("max_score must fit Numeric(8,3)")
        return self


class TeacherAssessmentRead(BaseModel):
    id: UUID
    course_offering_id: UUID
    section_id: UUID
    grading_period_id: UUID
    assessment_category_id: UUID
    code: str
    title: str
    max_score: float
    due_on: date | None
    status: str


class TeacherAssessmentStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status: Literal["DRAFT", "PUBLISHED", "CLOSED", "ARCHIVED"]
    status: Literal["DRAFT", "PUBLISHED", "CLOSED", "ARCHIVED"]
    operation_id: UUID


class TeacherGradeMark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_section_assignment_id: UUID
    score: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    status: str = Field(
        default="PENDING",
        pattern="^(PENDING|GRADED|MISSING|EXCUSED)$",
    )
    feedback: str | None = Field(default=None, max_length=1000)
    expected_revision: int = Field(default=0, ge=0)
    operation_id: UUID
    correction_reason: Literal["DATA_ENTRY_ERROR", "EVIDENCE_CORRECTION"] | None = None

    @model_validator(mode="after")
    def valid_score_precision(self):
        if self.score is not None:
            from decimal import Decimal

            value = Decimal(str(self.score))
            if value > Decimal("99999.999") or value.quantize(Decimal("0.001")) != value:
                raise ValueError("score must fit Numeric(8,3)")
        return self


class TeacherGradeRow(BaseModel):
    student_section_assignment_id: UUID
    student_profile_id: UUID
    student_code: str | None
    student_name: str
    grade_entry_id: UUID | None
    score: float | None
    status: str
    feedback: str | None
    revision: int


class TeacherAlert(BaseModel):
    signal_id: UUID
    student_profile_id: UUID
    student_name: str
    student_code: str | None
    section_id: UUID | None
    section_name: str | None
    signal_type: str
    severity: str
    summary: str
    metric_value: float
    threshold_value: float
    last_seen_at: datetime


class TeacherTaskRead(BaseModel):
    id: UUID
    automation_case_id: UUID
    student_profile_id: UUID
    student_name: str
    student_code: str | None
    section_id: UUID | None
    section_name: str | None
    title: str
    description: str | None
    status: str
    due_at: datetime
    escalate_at: datetime
    acknowledged_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None


class TeacherTaskComplete(BaseModel):
    completion_note: str = Field(min_length=3, max_length=1000)
