from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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


class AccountabilityReview(SQLModel, table=True):
    __tablename__ = "accountability_reviews"
    __table_args__ = (
        UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_reviews_idempotency"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    case_id: UUID = Field(foreign_key="accountability_cases.id", index=True)
    reviewer_user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    effective_permission_context_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    reviewed_at: datetime = Field(index=True)
    disposition: str = Field(max_length=32, index=True)
    evidence_refs_json: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    evidence_fingerprint_sha256: str = Field(max_length=64)
    source_version: int = Field(default=1, ge=1)
    projection_version: int = Field(default=1, ge=1)
    policy_key: str | None = Field(default=None, max_length=120)
    policy_version: int | None = Field(default=None, ge=1)
    note_reference: str | None = Field(default=None, max_length=240)
    next_required_step: str = Field(max_length=100)
    idempotency_key: str = Field(max_length=64, index=True)
    provenance_sha256: str = Field(max_length=64)
    canonical_event_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AccountabilityDecision(SQLModel, table=True):
    __tablename__ = "accountability_decisions"
    __table_args__ = (
        UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_decisions_idempotency"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    case_id: UUID = Field(foreign_key="accountability_cases.id", index=True)
    decision_actor_user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    review_id: UUID = Field(foreign_key="accountability_reviews.id", index=True)
    effective_permission_context_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    recorded_at: datetime = Field(index=True)
    decision_type: str = Field(max_length=32, index=True)
    evidence_refs_json: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    evidence_fingerprint_sha256: str = Field(max_length=64)
    policy_key: str | None = Field(default=None, max_length=120)
    policy_version: int | None = Field(default=None, ge=1)
    reason_reference: str | None = Field(default=None, max_length=240)
    execution_required: bool = False
    idempotency_key: str = Field(max_length=64, index=True)
    provenance_sha256: str = Field(max_length=64)
    canonical_event_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AccountabilityOwnershipEvent(SQLModel, table=True):
    __tablename__ = "accountability_ownership_events"
    __table_args__ = (
        UniqueConstraint("institution_id", "case_id", "idempotency_key", name="uq_accountability_ownership_idempotency"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    case_id: UUID = Field(foreign_key="accountability_cases.id", index=True)
    event_type: str = Field(max_length=20, index=True)
    previous_owner_user_id: UUID | None = Field(default=None, index=True)
    new_owner_user_id: UUID | None = Field(default=None, index=True)
    changed_by_user_id: UUID = Field(foreign_key="user_accounts.id", index=True)
    changed_at: datetime = Field(index=True)
    reason_reference: str | None = Field(default=None, max_length=240)
    effective_permission_context_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    idempotency_key: str = Field(max_length=64, index=True)
    provenance_sha256: str = Field(max_length=64)
    canonical_event_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
