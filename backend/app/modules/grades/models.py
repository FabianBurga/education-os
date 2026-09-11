from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class GradingPeriod(SQLModel, table=True):
    __tablename__ = "grading_periods"
    __table_args__ = (
        UniqueConstraint(
            "academic_period_id",
            "code",
            name="uq_grading_periods_period_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    starts_on: date
    ends_on: date
    sequence: int = 1
    status: str = Field(default="PLANNED", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class GradingScale(SQLModel, table=True):
    __tablename__ = "grading_scales"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_grading_scales_inst_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    minimum_score: float = 0.0
    maximum_score: float = 10.0
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class GradingScaleBand(SQLModel, table=True):
    __tablename__ = "grading_scale_bands"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    grading_scale_id: UUID = Field(index=True)
    minimum_score: float
    maximum_score: float
    label: str = Field(max_length=100)
    result_code: str | None = Field(default=None, max_length=40)
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class AssessmentCategory(SQLModel, table=True):
    __tablename__ = "assessment_categories"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "grading_period_id",
            "code",
            name="uq_assessment_categories_course_period_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    course_offering_id: UUID = Field(index=True)
    grading_period_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    weight_percent: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class Assessment(SQLModel, table=True):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "grading_period_id",
            "code",
            name="uq_assessments_course_period_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    course_offering_id: UUID = Field(index=True)
    grading_period_id: UUID = Field(index=True)
    assessment_category_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    title: str = Field(max_length=160)
    max_score: float = 10.0
    due_on: date | None = None
    status: str = Field(default="DRAFT", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class GradeEntry(SQLModel, table=True):
    __tablename__ = "grade_entries"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "student_section_assignment_id",
            name="uq_grade_entries_assessment_student",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    assessment_id: UUID = Field(index=True)
    student_section_assignment_id: UUID = Field(index=True)
    score: float | None = None
    status: str = Field(default="PENDING", max_length=20)
    feedback: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
