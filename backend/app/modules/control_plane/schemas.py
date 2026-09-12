from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ControlPlaneHealth(BaseModel):
    release_id: str
    database_revision: str
    unledgered_outbox_count: int
    ledger_latest_position: int
    projection_position: int
    projection_lag: int
    capability_drift_count: int
    status: str


class ControlPlaneSummary(BaseModel):
    organization_id: UUID
    institution_id: UUID
    institution_name: str
    institution_type: str
    institution_status: str
    control_revision: int
    capability_count: int
    capabilities_enabled: int
    capabilities_disabled: int
    policies_total: int
    policies_enabled: int
    health: ControlPlaneHealth


class CapabilityControlRead(BaseModel):
    capability_key: str
    enabled: bool
    managed_revision: int | None = None
    managed_enabled: bool | None = None
    drift: bool = False


class CapabilityControlUpdate(BaseModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=500)


class PolicyControlRead(BaseModel):
    policy_key: str
    enabled: bool
    policy: dict[str, Any]
    policy_version: int
    managed_revision: int | None = None
    updated_at: datetime


class PolicyControlUpdate(BaseModel):
    enabled: bool = True
    policy: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=500)


class ControlChangeRead(BaseModel):
    revision: int
    change_type: str
    subject_key: str
    actor_user_id: UUID | None
    reason: str
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: datetime
