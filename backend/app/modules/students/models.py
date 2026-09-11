from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class StudentProfile(SQLModel, table=True):
    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "person_id",
            name="uq_student_profiles_institution_person",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    person_id: UUID = Field(index=True)
    student_code: str | None = Field(default=None, max_length=64)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
