from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AttendanceCode(SQLModel, table=True):
    __tablename__ = "attendance_codes"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_attendance_codes_inst_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=24)
    label: str = Field(max_length=80)
    semantic: str = Field(max_length=20)
    counts_as_present: bool = False
    counts_as_absent: bool = False
    counts_as_late: bool = False
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class ClassSession(SQLModel, table=True):
    __tablename__ = "class_sessions"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "session_date",
            "starts_at",
            name="uq_class_sessions_course_date_start",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    course_offering_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    schedule_slot_id: UUID | None = Field(default=None, index=True)
    session_date: date
    starts_at: time
    ends_at: time
    status: str = Field(default="OPEN", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class AttendanceRecord(SQLModel, table=True):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "class_session_id",
            "student_section_assignment_id",
            name="uq_attendance_records_session_student",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    class_session_id: UUID = Field(index=True)
    student_section_assignment_id: UUID = Field(index=True)
    attendance_code_id: UUID = Field(index=True)
    minutes_late: int = 0
    note: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
