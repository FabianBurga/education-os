from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AcademicLevel(SQLModel, table=True):
    __tablename__ = "academic_levels"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_academic_levels_inst_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    sort_order: int = 0
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class GradeLevel(SQLModel, table=True):
    __tablename__ = "grade_levels"
    __table_args__ = (UniqueConstraint("institution_id", "code", name="uq_grade_levels_inst_code"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_level_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    sort_order: int = 0
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Subject(SQLModel, table=True):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("institution_id", "code", name="uq_subjects_inst_code"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=160)
    area: str | None = Field(default=None, max_length=120)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class Section(SQLModel, table=True):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint(
            "academic_period_id",
            "campus_id",
            "grade_level_id",
            "code",
            name="uq_sections_period_campus_grade_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    campus_id: UUID = Field(index=True)
    grade_level_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=120)
    shift: str | None = Field(default=None, max_length=20)
    capacity: int = 40
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class CurriculumPlan(SQLModel, table=True):
    __tablename__ = "curriculum_plans"
    __table_args__ = (
        UniqueConstraint(
            "academic_period_id",
            "grade_level_id",
            "code",
            name="uq_curriculum_plans_period_grade_code",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    grade_level_id: UUID = Field(index=True)
    code: str = Field(max_length=40)
    name: str = Field(max_length=160)
    status: str = Field(default="DRAFT", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class CurriculumSubject(SQLModel, table=True):
    __tablename__ = "curriculum_subjects"
    __table_args__ = (
        UniqueConstraint(
            "curriculum_plan_id",
            "subject_id",
            name="uq_curriculum_subjects_plan_subject",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    curriculum_plan_id: UUID = Field(index=True)
    subject_id: UUID = Field(index=True)
    weekly_periods: int = 0
    is_required: bool = True
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class CourseOffering(SQLModel, table=True):
    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint("section_id", "subject_id", name="uq_course_offerings_section_subject"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    subject_id: UUID = Field(index=True)
    curriculum_subject_id: UUID | None = Field(default=None, index=True)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class TeachingAssignment(SQLModel, table=True):
    __tablename__ = "teaching_assignments"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "staff_profile_id",
            name="uq_teaching_assignments_course_staff",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    course_offering_id: UUID = Field(index=True)
    staff_profile_id: UUID = Field(index=True)
    assignment_role: str = Field(default="LEAD", max_length=20)
    starts_on: date | None = None
    ends_on: date | None = None
    created_at: datetime = Field(default_factory=utcnow)


class StudentSectionAssignment(SQLModel, table=True):
    __tablename__ = "student_section_assignments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID = Field(index=True)
    enrollment_id: UUID = Field(index=True)
    section_id: UUID = Field(index=True)
    status: str = Field(default="ACTIVE", max_length=20)
    assigned_on: date
    ended_on: date | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ScheduleSlot(SQLModel, table=True):
    __tablename__ = "schedule_slots"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "weekday",
            "starts_at",
            name="uq_schedule_slots_course_day_start",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    course_offering_id: UUID = Field(index=True)
    weekday: int
    starts_at: time
    ends_at: time
    room_label: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=utcnow)
