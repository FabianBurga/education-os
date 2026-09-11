from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GuardianMe(BaseModel):
    guardian_profile_id: UUID
    given_names: str
    family_names: str
    linked_children: int


class ChildCard(BaseModel):
    student_profile_id: UUID
    given_names: str
    family_names: str
    relationship_type: str | None
    academic_period_name: str | None
    grade_name: str | None
    section_name: str | None


class ChildOverview(BaseModel):
    student_profile_id: UUID
    attendance_rate: float | None
    absence_count: int
    late_count: int
    academic_average_percent: float | None
    missing_assessments: int
    graded_entries: int


class AttendanceItem(BaseModel):
    session_date: date
    subject_name: str | None
    code: str
    label: str
    semantic: str
    minutes_late: int


class GradeItem(BaseModel):
    assessment_id: UUID
    subject_name: str | None
    grading_period_name: str | None
    title: str
    due_on: date | None
    max_score: float
    score: float | None
    status: str
    feedback: str | None


class PortalGrantCreate(BaseModel):
    guardian_profile_id: UUID
    student_profile_id: UUID
    access_level: str = Field(default="STANDARD", pattern="^(STANDARD|LIMITED)$")


class PortalGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    institution_id: UUID
    guardian_profile_id: UUID
    student_profile_id: UUID
    access_level: str
    status: str
    granted_at: datetime
    revoked_at: datetime | None


class BootstrapAccessResult(BaseModel):
    created: int
    existing: int


class FamilyNoticeCreate(BaseModel):
    student_profile_id: UUID | None = None
    notice_type: str = Field(
        default="GENERAL",
        pattern="^(GENERAL|ANNOUNCEMENT|REMINDER|ACADEMIC|ATTENDANCE)$",
    )
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    requires_acknowledgement: bool = False
    publish_now: bool = False


class FamilyNoticeRead(BaseModel):
    id: UUID
    student_profile_id: UUID | None
    notice_type: str
    title: str
    body: str
    requires_acknowledgement: bool
    published_at: datetime | None
    read_at: datetime | None
    acknowledged_at: datetime | None


class StaffNoticeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    institution_id: UUID
    student_profile_id: UUID | None
    notice_type: str
    title: str
    body: str
    requires_acknowledgement: bool
    status: str
    published_at: datetime | None
    created_by_user_id: UUID | None
    created_at: datetime


class NoticeAcknowledgeResult(BaseModel):
    family_notice_id: UUID
    guardian_profile_id: UUID
    acknowledged_at: datetime
