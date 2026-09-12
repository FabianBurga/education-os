from uuid import UUID

from pydantic import BaseModel


class UiUserIdentity(BaseModel):
    user_id: UUID
    display_name: str
    login_email: str


class UiTenantContext(BaseModel):
    organization_id: UUID
    organization_name: str
    institution_id: UUID
    institution_name: str
    institution_type: str


class UiProfileContext(BaseModel):
    staff: bool
    student: bool
    guardian: bool


class UiBootstrapRead(BaseModel):
    user: UiUserIdentity
    tenant: UiTenantContext
    roles: list[str]
    permissions: list[str]
    capabilities: dict[str, bool]
    profiles: UiProfileContext
