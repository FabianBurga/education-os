from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class CommunicationTemplate(SQLModel, table=True):
    __tablename__ = "communication_templates"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "name",
            name="uq_communication_templates_inst_name",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    name: str = Field(max_length=160)
    title_template: str = Field(max_length=200)
    body_template: str = Field(max_length=4000)
    notice_type: str = Field(default="ANNOUNCEMENT", max_length=30)
    requires_acknowledgement: bool = False
    status: str = Field(default="ACTIVE", max_length=20)
    created_by_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Communication(SQLModel, table=True):
    __tablename__ = "communications"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    template_id: UUID | None = Field(default=None, index=True)
    title: str = Field(max_length=200)
    body: str = Field(max_length=4000)
    notice_type: str = Field(default="ANNOUNCEMENT", max_length=30)
    requires_acknowledgement: bool = False
    status: str = Field(default="DRAFT", max_length=20)
    created_by_user_id: UUID | None = None
    published_by_user_id: UUID | None = None
    published_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CommunicationTarget(SQLModel, table=True):
    __tablename__ = "communication_targets"
    __table_args__ = (
        UniqueConstraint(
            "communication_id",
            "target_type",
            "target_id",
            name="uq_communication_targets_scope",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    communication_id: UUID = Field(index=True)
    target_type: str = Field(max_length=20)
    target_id: UUID = Field(index=True)
    target_label: str = Field(max_length=240)
    created_at: datetime = Field(default_factory=utcnow)


class CommunicationRecipient(SQLModel, table=True):
    __tablename__ = "communication_recipients"
    __table_args__ = (
        UniqueConstraint(
            "communication_id",
            "guardian_profile_id",
            "student_profile_id",
            name="uq_communication_recipient_guardian_student",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    communication_id: UUID = Field(index=True)
    guardian_profile_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    family_notice_id: UUID = Field(index=True)
    delivery_status: str = Field(default="DELIVERED", max_length=20)
    delivered_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
