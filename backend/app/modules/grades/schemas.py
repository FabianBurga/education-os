from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    institution_id: UUID


class GradingPeriodCreate(BaseModel):
    academic_period_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    starts_on: date
    ends_on: date
    sequence: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class GradingPeriodRead(TenantRead):
    academic_period_id: UUID
    code: str
    name: str
    starts_on: date
    ends_on: date
    sequence: int
    status: str


class GradingScaleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    minimum_score: float = 0.0
    maximum_score: float = 10.0

    @model_validator(mode="after")
    def valid_range(self):
        if self.maximum_score <= self.minimum_score:
            raise ValueError("maximum_score must be greater than minimum_score")
        return self


class GradingScaleRead(TenantRead):
    code: str
    name: str
    minimum_score: float
    maximum_score: float
    status: str


class GradingScaleBandCreate(BaseModel):
    minimum_score: float
    maximum_score: float
    label: str = Field(min_length=1, max_length=100)
    result_code: str | None = Field(default=None, max_length=40)
    sort_order: int = 0

    @model_validator(mode="after")
    def valid_range(self):
        if self.maximum_score < self.minimum_score:
            raise ValueError("maximum_score must be >= minimum_score")
        return self


class GradingScaleBandRead(TenantRead):
    grading_scale_id: UUID
    minimum_score: float
    maximum_score: float
    label: str
    result_code: str | None
    sort_order: int


class AssessmentCategoryCreate(BaseModel):
    course_offering_id: UUID
    grading_period_id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    weight_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class AssessmentCategoryRead(TenantRead):
    section_id: UUID
    course_offering_id: UUID
    grading_period_id: UUID
    code: str
    name: str
    weight_percent: float


class AssessmentCreate(BaseModel):
    course_offering_id: UUID
    grading_period_id: UUID
    assessment_category_id: UUID
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    max_score: float = Field(default=10.0, gt=0.0)
    due_on: date | None = None


class AssessmentRead(TenantRead):
    section_id: UUID
    course_offering_id: UUID
    grading_period_id: UUID
    assessment_category_id: UUID
    code: str
    title: str
    max_score: float
    due_on: date | None
    status: str


class GradeEntryUpsert(BaseModel):
    student_section_assignment_id: UUID
    score: float | None = Field(default=None, ge=0.0)
    status: str = Field(
        default="PENDING",
        pattern="^(PENDING|GRADED|MISSING|EXCUSED)$",
    )
    feedback: str | None = Field(default=None, max_length=1000)


class GradeEntryRead(TenantRead):
    section_id: UUID
    assessment_id: UUID
    student_section_assignment_id: UUID
    score: float | None
    status: str
    feedback: str | None
