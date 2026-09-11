from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    institution_id: UUID


class AcademicLevelCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class AcademicLevelRead(TenantRead):
    code: str
    name: str
    sort_order: int
    status: str


class GradeLevelCreate(BaseModel):
    academic_level_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class GradeLevelRead(TenantRead):
    academic_level_id: UUID
    code: str
    name: str
    sort_order: int
    status: str


class SubjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    area: str | None = Field(default=None, max_length=120)


class SubjectRead(TenantRead):
    code: str
    name: str
    area: str | None
    status: str


class SectionCreate(BaseModel):
    academic_period_id: UUID
    campus_id: UUID
    grade_level_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    shift: str | None = Field(
        default=None,
        pattern="^(MORNING|AFTERNOON|EVENING|FULL_DAY)$",
    )
    capacity: int = Field(default=40, gt=0, le=500)


class SectionRead(TenantRead):
    academic_period_id: UUID
    campus_id: UUID
    grade_level_id: UUID
    code: str
    name: str
    shift: str | None
    capacity: int
    status: str


class CurriculumPlanCreate(BaseModel):
    academic_period_id: UUID
    grade_level_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    status: str = Field(default="DRAFT", pattern="^(DRAFT|ACTIVE|ARCHIVED)$")


class CurriculumPlanRead(TenantRead):
    academic_period_id: UUID
    grade_level_id: UUID
    code: str
    name: str
    status: str


class CurriculumSubjectCreate(BaseModel):
    subject_id: UUID
    weekly_periods: int = Field(default=0, ge=0, le=60)
    is_required: bool = True
    sort_order: int = 0


class CurriculumSubjectRead(TenantRead):
    curriculum_plan_id: UUID
    subject_id: UUID
    weekly_periods: int
    is_required: bool
    sort_order: int


class CourseOfferingCreate(BaseModel):
    section_id: UUID
    subject_id: UUID
    curriculum_subject_id: UUID | None = None


class CourseOfferingRead(TenantRead):
    academic_period_id: UUID
    section_id: UUID
    subject_id: UUID
    curriculum_subject_id: UUID | None
    status: str


class TeachingAssignmentCreate(BaseModel):
    course_offering_id: UUID
    staff_profile_id: UUID
    assignment_role: str = Field(
        default="LEAD",
        pattern="^(LEAD|CO_TEACHER|SUPPORT)$",
    )
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class TeachingAssignmentRead(TenantRead):
    course_offering_id: UUID
    staff_profile_id: UUID
    assignment_role: str
    starts_on: date | None
    ends_on: date | None


class StudentSectionAssignmentCreate(BaseModel):
    enrollment_id: UUID
    section_id: UUID
    assigned_on: date


class StudentSectionAssignmentRead(TenantRead):
    academic_period_id: UUID
    enrollment_id: UUID
    section_id: UUID
    status: str
    assigned_on: date
    ended_on: date | None


class ScheduleSlotCreate(BaseModel):
    course_offering_id: UUID
    weekday: int = Field(ge=1, le=7)
    starts_at: time
    ends_at: time
    room_label: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ScheduleSlotRead(TenantRead):
    course_offering_id: UUID
    weekday: int
    starts_at: time
    ends_at: time
    room_label: str | None
