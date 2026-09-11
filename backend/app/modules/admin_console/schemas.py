from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstitutionAdminRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    type: str
    status: str


class InstitutionAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(
        default=None,
        pattern="^(PRIVATE|PUBLIC|FISCOMISIONAL|MUNICIPAL)$",
    )
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class CampusAdminCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CampusAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    institution_id: UUID
    name: str


class PersonAdminCreate(BaseModel):
    given_names: str = Field(min_length=1, max_length=160)
    family_names: str = Field(min_length=1, max_length=160)
    primary_email: str | None = Field(default=None, max_length=320)


class PersonAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    given_names: str
    family_names: str
    primary_email: str | None
    created_at: datetime


class AccountAdminCreate(BaseModel):
    person_id: UUID
    login_email: str = Field(min_length=3, max_length=320)
    temporary_password: str = Field(min_length=10, max_length=256)


class AccountAdminRead(BaseModel):
    user_id: UUID
    person_id: UUID
    membership_id: UUID
    login_email: str
    is_active: bool
    status: str
    roles: list[str] = Field(default_factory=list)


class StaffAdminCreate(BaseModel):
    person_id: UUID
    staff_code: str | None = Field(default=None, max_length=64)


class StaffAdminRead(BaseModel):
    id: UUID
    person_id: UUID
    staff_code: str | None
    status: str


class RoleAdminCreate(BaseModel):
    key: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    name: str = Field(min_length=2, max_length=160)


class RoleAdminRead(BaseModel):
    id: UUID
    key: str
    name: str
    permissions: list[str] = Field(default_factory=list)


class PermissionAdminRead(BaseModel):
    id: UUID
    key: str
    description: str


class AdminSummary(BaseModel):
    people: int
    users: int
    active_staff: int
    active_students: int
    active_guardians: int
    campuses: int
    academic_periods: int
    sections: int
    subjects: int
    roles: int


class ChecklistItem(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str


class OnboardingChecklist(BaseModel):
    ready_items: int
    total_items: int
    completion_percent: float
    items: list[ChecklistItem]
