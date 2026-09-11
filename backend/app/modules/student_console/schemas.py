from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel


class StudentProfileRead(BaseModel):
    student_profile_id: UUID
    student_code: str | None
    student_name: str
    primary_email: str | None
    enrollment_number: str | None
    academic_period_id: UUID | None
    academic_period_name: str | None
    campus_name: str | None
    grade_name: str | None
    section_name: str | None


class StudentSummary(BaseModel):
    active_classes: int
    schedule_slots: int
    attendance_present: int
    attendance_absent: int
    attendance_late: int
    academic_average_percent: float | None
    pending_assessments: int
    published_notices: int


class StudentClassRead(BaseModel):
    course_offering_id: UUID
    subject_code: str
    subject_name: str
    subject_area: str | None
    grade_name: str
    section_name: str
    academic_period_name: str
    teachers: list[str]


class StudentScheduleRead(BaseModel):
    schedule_slot_id: UUID
    course_offering_id: UUID
    weekday: int
    starts_at: time
    ends_at: time
    room_label: str | None
    subject_name: str
    subject_code: str
    section_name: str


class StudentAttendanceRead(BaseModel):
    attendance_record_id: UUID
    class_session_id: UUID
    course_offering_id: UUID
    session_date: date
    starts_at: time
    ends_at: time
    subject_name: str
    subject_code: str
    attendance_code: str
    attendance_label: str
    semantic: str
    minutes_late: int
    note: str | None


class StudentGradeRead(BaseModel):
    assessment_id: UUID
    grade_entry_id: UUID | None
    course_offering_id: UUID
    subject_name: str
    subject_code: str
    grading_period_name: str
    category_name: str
    assessment_code: str
    assessment_title: str
    max_score: float
    due_on: date | None
    score: float | None
    status: str
    feedback: str | None
    percentage: float | None


class StudentPendingRead(BaseModel):
    assessment_id: UUID
    course_offering_id: UUID
    subject_name: str
    subject_code: str
    assessment_title: str
    due_on: date | None
    status: str
    overdue: bool


class StudentProgressRead(BaseModel):
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


class StudentNoticeRead(BaseModel):
    notice_id: UUID
    notice_type: str
    title: str
    body: str
    requires_acknowledgement: bool
    published_at: datetime | None
    is_personal: bool
