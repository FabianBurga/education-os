from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class AccountabilityCase(SQLModel, table=True):
    __tablename__ = "accountability_cases"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "identity_version",
            "identity_key_sha256",
            name="uq_accountability_cases_identity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    subject_type: str = Field(max_length=80, index=True)
    subject_id: UUID = Field(index=True)
    source_category: str = Field(max_length=120, index=True)
    normalized_category: str = Field(max_length=120, index=True)
    category_mapping_version: int = Field(default=1, ge=1)
    identity_version: int = Field(default=1, ge=1)
    identity_key_sha256: str = Field(max_length=64, index=True)
    episode_anchor: str = Field(max_length=180)
    lifecycle: str = Field(default="OPEN", max_length=30, index=True)
    owner_state: str = Field(default="UNASSIGNED", max_length=20, index=True)
    primary_owner_user_id: UUID | None = Field(default=None, index=True)
    recurrence_classification: str = Field(default="NEW_EPISODE", max_length=30)
    related_case_id: UUID | None = Field(default=None, index=True)
    projection_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class AccountabilityCaseSource(SQLModel, table=True):
    __tablename__ = "accountability_case_sources"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "source_fingerprint_sha256",
            name="uq_accountability_case_sources_fingerprint",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    case_id: UUID = Field(foreign_key="accountability_cases.id", index=True)
    source_kind: str = Field(max_length=30, index=True)
    source_entity_id: UUID = Field(index=True)
    source_event_id: UUID | None = Field(default=None, index=True)
    source_event_version: int = Field(default=1, ge=1)
    source_category: str = Field(max_length=120)
    source_provenance_sha256: str = Field(max_length=64)
    source_fingerprint_sha256: str = Field(max_length=64)
    observed_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
