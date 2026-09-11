from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel


class GuardianConsoleMe(BaseModel):
    guardian_profile_id: UUID
    guardian_name: str
    primary_email: str | None
    linked_students: int


class GuardianStudentCard(BaseModel):
    student_profile_id: UUID
    student_name: str
    student_code: str | None
    access_level: str
    relationship_type: str | None
    academic_period_name: str | None
    grade_name: str | None
    section_name: str | None


class GuardianStudentSummary(BaseModel):
    student_profile_id: UUID
    attendance_present: int
    attendance_absent: int
    attendance_late: int
    attendance_rate: float | None
    academic_average_percent: float | None
    pending_assessments: int
    visible_notices: int


class GuardianClassRead(BaseModel):
    course_offering_id: UUID
    subject_code: str
    subject_name: str
    subject_area: str | None
    section_name: str
    teachers: list[str]


class GuardianScheduleRead(BaseModel):
    schedule_slot_id: UUID
    course_offering_id: UUID
    weekday: int
    starts_at: time
    ends_at: time
    room_label: str | None
    subject_name: str
    subject_code: str


class GuardianAttendanceRead(BaseModel):
    attendance_record_id: UUID
    session_date: date
    subject_name: str
    subject_code: str
    attendance_code: str
    attendance_label: str
    semantic: str
    minutes_late: int
    note: str | None


class GuardianGradeRead(BaseModel):
    assessment_id: UUID
    grade_entry_id: UUID | None
    subject_name: str
    subject_code: str
    grading_period_name: str
    category_name: str
    assessment_title: str
    due_on: date | None
    max_score: float
    score: float | None
    status: str
    feedback: str | None
    percentage: float | None


class GuardianPendingRead(BaseModel):
    assessment_id: UUID
    subject_name: str
    subject_code: str
    assessment_title: str
    due_on: date | None
    status: str
    overdue: bool


class GuardianProgressRead(BaseModel):
    course_offering_id: UUID
    subject_name: str
    subject_code: str
    academic_average_percent: float | None
    graded_items: int
    missing_items: int
    attendance_records: int
    present_records: int
    absent_records: int
    late_records: int


class GuardianNoticeRead(BaseModel):
    notice_id: UUID
    student_profile_id: UUID | None
    notice_type: str
    title: str
    body: str
    requires_acknowledgement: bool
    published_at: datetime | None
    read_at: datetime | None
    acknowledged_at: datetime | None
    scope: str


class GuardianNoticeAcknowledge(BaseModel):
    notice_id: UUID
    guardian_profile_id: UUID
    acknowledged_at: datetime
