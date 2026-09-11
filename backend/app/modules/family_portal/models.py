from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class GuardianStudentPortalAccess(SQLModel, table=True):
    __tablename__ = "guardian_student_portal_access"
    __table_args__ = (
        UniqueConstraint(
            "guardian_profile_id",
            "student_profile_id",
            name="uq_guardian_student_portal_access_pair",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    guardian_profile_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    access_level: str = Field(default="STANDARD", max_length=20)
    status: str = Field(default="ACTIVE", max_length=20)
    granted_at: datetime = Field(default_factory=utcnow)
    revoked_at: datetime | None = None


class FamilyNotice(SQLModel, table=True):
    __tablename__ = "family_notices"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID | None = Field(default=None, index=True)
    notice_type: str = Field(default="GENERAL", max_length=30)
    title: str = Field(max_length=200)
    body: str = Field(max_length=4000)
    requires_acknowledgement: bool = False
    status: str = Field(default="DRAFT", max_length=20)
    published_at: datetime | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)


class FamilyNoticeReceipt(SQLModel, table=True):
    __tablename__ = "family_notice_receipts"
    __table_args__ = (
        UniqueConstraint(
            "family_notice_id",
            "guardian_profile_id",
            name="uq_family_notice_receipt_notice_guardian",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    family_notice_id: UUID = Field(index=True)
    guardian_profile_id: UUID = Field(index=True)
    read_at: datetime | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
