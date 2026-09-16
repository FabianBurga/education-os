from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)


def _reject_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(marker in str(key).lower() for marker in _SECRET_MARKERS):
                raise ValueError("Integration configuration must not contain secret material")
            _reject_secrets(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secrets(nested)
    return value


class IntegrationConnectorCreate(BaseModel):
    connector_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    connector_type: Literal["FILE_CSV", "CSV_STUDENT_ENROLLMENT"]
    display_name: str = Field(min_length=1, max_length=160)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("configuration")
    @classmethod
    def safe_configuration(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_secrets(value)


class IntegrationConnectorRead(BaseModel):
    id: UUID
    connector_key: str
    connector_type: str
    display_name: str
    status: str
    config_version: int
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class IntegrationRunRead(BaseModel):
    id: UUID
    connector_id: UUID
    connector_key: str
    connector_display_name: str
    mapping_id: UUID | None
    initiated_by_user_id: UUID
    source_kind: str
    mode: str
    source_filename: str | None
    source_fingerprint_sha256: str
    connector_config_version: int
    status: str
    total_rows: int = Field(ge=0, le=1000)
    valid_rows: int = Field(ge=0, le=1000)
    invalid_rows: int = Field(ge=0, le=1000)
    conflict_rows: int = Field(ge=0, le=1000)
    applied_rows: int = Field(ge=0, le=1000)
    failed_rows: int = Field(ge=0, le=1000)
    created_at: datetime


class CsvStudentEnrollmentPreviewRead(BaseModel):
    run: IntegrationRunRead
    total_rows: int
    valid_rows: int
    invalid_rows: int
    conflict_rows: int


class IntegrationRunItemRead(BaseModel):
    id: UUID
    source_row_number: int | None = Field(default=None, ge=1, le=1001)
    external_student_id: str | None = Field(default=None, max_length=120)
    canonical_entity_type: str
    operation_class: str
    status: str
    error_code: str | None
    academic_period_code: str | None = Field(default=None, max_length=40)
    campus_id: UUID | None = None
    student_code: str | None = Field(default=None, max_length=64)
    idempotency_key: str | None = Field(default=None, min_length=64, max_length=64)
    student_profile_id: UUID | None = None
    enrollment_id: UUID | None = None
    created_at: datetime


class IntegrationRunEventMetadataRead(BaseModel):
    workflow: str | None = Field(default=None, max_length=80)
    source_filename: str | None = Field(default=None, max_length=160)
    source_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    total_rows: int | None = Field(default=None, ge=0, le=1000)
    valid_rows: int | None = Field(default=None, ge=0, le=1000)
    invalid_rows: int | None = Field(default=None, ge=0, le=1000)
    conflict_rows: int | None = Field(default=None, ge=0, le=1000)
    dry_run: bool | None = None
    external_student_id: str | None = Field(default=None, max_length=120)
    student_profile_id: UUID | None = None
    enrollment_id: UUID | None = None
    error_code: str | None = Field(default=None, max_length=80)
    applied_at: datetime | None = None


class IntegrationRunEventRead(BaseModel):
    sequence: int = Field(ge=1)
    event_type: str
    run_item_id: UUID | None
    actor_user_id: UUID | None
    created_at: datetime
    metadata: IntegrationRunEventMetadataRead
