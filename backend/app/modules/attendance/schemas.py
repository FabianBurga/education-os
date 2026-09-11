from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID


class AttendanceCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    label: str = Field(min_length=1, max_length=80)
    semantic: str = Field(pattern="^(PRESENT|ABSENT|LATE|EXCUSED|REMOTE|OTHER)$")
    counts_as_present: bool = False
    counts_as_absent: bool = False
    counts_as_late: bool = False


class AttendanceCodeRead(TenantRead):
    code: str
    label: str
    semantic: str
    counts_as_present: bool
    counts_as_absent: bool
    counts_as_late: bool
    status: str


class ClassSessionCreate(BaseModel):
    course_offering_id: UUID
    schedule_slot_id: UUID | None = None
    session_date: date
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ClassSessionRead(TenantRead):
    course_offering_id: UUID
    section_id: UUID
    schedule_slot_id: UUID | None
    session_date: date
    starts_at: time
    ends_at: time
    status: str


class AttendanceRecordUpsert(BaseModel):
    student_section_assignment_id: UUID
    attendance_code_id: UUID
    minutes_late: int = Field(default=0, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=500)


class AttendanceRecordRead(TenantRead):
    section_id: UUID
    class_session_id: UUID
    student_section_assignment_id: UUID
    attendance_code_id: UUID
    minutes_late: int
    note: str | None
