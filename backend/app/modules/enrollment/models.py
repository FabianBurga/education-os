from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AcademicPeriod(SQLModel, table=True):
    __tablename__ = "academic_periods"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "code",
            name="uq_academic_periods_institution_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    starts_on: date
    ends_on: date
    status: str = Field(default="PLANNED", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id",
            "academic_period_id",
            name="uq_enrollments_student_period",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    campus_id: UUID = Field(index=True)
    enrollment_number: str | None = Field(default=None, max_length=64)
    status: str = Field(default="PENDING", max_length=20)
    enrolled_on: date | None = None
    withdrawn_on: date | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
