from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

NoticeType = Literal[
    "GENERAL",
    "ANNOUNCEMENT",
    "REMINDER",
    "ACADEMIC",
    "ATTENDANCE",
]
TargetType = Literal[
    "INSTITUTION",
    "CAMPUS",
    "SECTION",
    "COURSE",
    "STUDENT",
    "FAMILY",
]


class CommunicationTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    title_template: str = Field(min_length=2, max_length=200)
    body_template: str = Field(min_length=2, max_length=4000)
    notice_type: NoticeType = "ANNOUNCEMENT"
    requires_acknowledgement: bool = False


class CommunicationTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    title_template: str | None = Field(default=None, min_length=2, max_length=200)
    body_template: str | None = Field(default=None, min_length=2, max_length=4000)
    notice_type: NoticeType | None = None
    requires_acknowledgement: bool | None = None
    status: Literal["ACTIVE", "ARCHIVED"] | None = None


class CommunicationTemplateRead(BaseModel):
    id: UUID
    name: str
    title_template: str
    body_template: str
    notice_type: str
    requires_acknowledgement: bool
    status: str
    created_at: datetime
    updated_at: datetime


class CommunicationCreate(BaseModel):
    template_id: UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=2, max_length=4000)
    notice_type: NoticeType = "ANNOUNCEMENT"
    requires_acknowledgement: bool = False


class CommunicationUpdate(BaseModel):
    template_id: UUID | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    body: str | None = Field(default=None, min_length=2, max_length=4000)
    notice_type: NoticeType | None = None
    requires_acknowledgement: bool | None = None


class CommunicationTargetSpec(BaseModel):
    target_type: TargetType
    target_id: UUID


class CommunicationTargetsReplace(BaseModel):
    targets: list[CommunicationTargetSpec] = Field(min_length=1, max_length=50)


class CommunicationTargetRead(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    target_label: str


class CommunicationRead(BaseModel):
    id: UUID
    template_id: UUID | None
    title: str
    body: str
    notice_type: str
    requires_acknowledgement: bool
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    target_count: int
    recipient_count: int


class CommunicationDetail(CommunicationRead):
    targets: list[CommunicationTargetRead]


class CommunicationSummary(BaseModel):
    draft_messages: int
    published_messages: int
    archived_messages: int
    active_templates: int
    delivered_recipients: int
    read_recipients: int
    acknowledged_recipients: int


class TargetOption(BaseModel):
    id: UUID
    label: str
    secondary: str | None = None


class CommunicationPreview(BaseModel):
    communication_id: UUID
    target_count: int
    target_students: int
    reachable_students: int
    guardian_recipients: int
    unreachable_students: int


class CommunicationPublishResult(BaseModel):
    communication_id: UUID
    published_at: datetime
    students_reached: int
    guardian_recipients: int
    family_notices_created: int


class DeliveryRecipientRead(BaseModel):
    guardian_profile_id: UUID
    guardian_name: str
    student_profile_id: UUID
    student_name: str
    family_notice_id: UUID
    status: Literal["DELIVERED", "READ", "ACKNOWLEDGED"]
    delivered_at: datetime
    read_at: datetime | None
    acknowledged_at: datetime | None


class CommunicationDeliveryReport(BaseModel):
    communication_id: UUID
    title: str
    requires_acknowledgement: bool
    recipients_total: int
    delivered: int
    read: int
    acknowledged: int
    recipients: list[DeliveryRecipientRead]
