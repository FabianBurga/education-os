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
    mapping_id: UUID | None
    initiated_by_user_id: UUID
    source_kind: str
    mode: str
    source_fingerprint_sha256: str
    idempotency_key: str
    connector_config_version: int
    status: str
    created_at: datetime


class CsvStudentEnrollmentPreviewRead(BaseModel):
    run: IntegrationRunRead
    total_rows: int
    valid_rows: int
    invalid_rows: int
    conflict_rows: int


class IntegrationRunItemRead(BaseModel):
    id: UUID
    source_item_key: str
    canonical_entity_type: str
    operation_class: str
    status: str
    error_code: str | None
    detail: dict[str, Any]
    result_entity_id: UUID | None
    created_at: datetime
