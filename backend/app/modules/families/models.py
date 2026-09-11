from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class GuardianProfile(SQLModel, table=True):
    __tablename__ = "guardian_profiles"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "person_id",
            name="uq_guardian_profiles_institution_person",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    person_id: UUID = Field(index=True)
    guardian_code: str | None = Field(default=None, max_length=64)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class StaffProfile(SQLModel, table=True):
    __tablename__ = "staff_profiles"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "person_id",
            name="uq_staff_profiles_institution_person",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    person_id: UUID = Field(index=True)
    staff_code: str | None = Field(default=None, max_length=64)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class FamilyHousehold(SQLModel, table=True):
    __tablename__ = "family_households"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    name: str = Field(max_length=120)
    status: str = Field(default="ACTIVE", max_length=20)
    created_at: datetime = Field(default_factory=utcnow)


class FamilyMember(SQLModel, table=True):
    __tablename__ = "family_members"
    __table_args__ = (
        UniqueConstraint("family_id", "person_id", name="uq_family_members_family_person"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    family_id: UUID = Field(index=True)
    person_id: UUID = Field(index=True)
    member_role: str = Field(max_length=20)
    relationship_label: str | None = Field(default=None, max_length=40)
    created_at: datetime = Field(default_factory=utcnow)


class StudentGuardianRelationship(SQLModel, table=True):
    __tablename__ = "student_guardian_relationships"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id",
            "guardian_profile_id",
            name="uq_student_guardian_pair",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    guardian_profile_id: UUID = Field(index=True)
    relationship_type: str = Field(max_length=40)
    is_legal_guardian: bool = False
    is_primary_contact: bool = False
    lives_with_student: bool = False
    pickup_authorized: bool = False
    emergency_contact: bool = False
    created_at: datetime = Field(default_factory=utcnow)
