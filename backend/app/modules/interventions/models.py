from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Intervention(SQLModel, table=True):
    __tablename__ = "interventions"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_interventions_severity",
        ),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','MONITORING','RESOLVED','CLOSED','CANCELLED')",
            name="ck_interventions_status",
        ),
        CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_interventions_sensitivity",
        ),
        CheckConstraint(
            "origin_type IN ('HUMAN','SIGNAL','LEGACY_CASE','SYSTEM_SUGGESTION')",
            name="ck_interventions_origin_type",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    section_id: UUID | None = Field(default=None, index=True)

    intervention_type: str = Field(max_length=60)
    severity: str = Field(default="MEDIUM", max_length=20)
    status: str = Field(default="OPEN", max_length=30)
    sensitivity: str = Field(default="GENERAL", max_length=20)

    title: str = Field(max_length=240)
    reason: str = Field(max_length=2000)
    objective: str | None = Field(default=None, max_length=2000)
    origin_type: str = Field(max_length=30)

    opened_by_user_id: UUID
    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = Field(default=None, index=True)

    opened_at: datetime = Field(default_factory=utcnow)
    target_at: datetime | None = Field(default=None, index=True)
    resolved_at: datetime | None = None
    closed_at: datetime | None = None

    outcome_type: str | None = Field(default=None, max_length=30)
    outcome_summary: str | None = Field(default=None, max_length=2000)
    outcome_recorded_at: datetime | None = None
    outcome_recorded_by_user_id: UUID | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class InterventionLink(SQLModel, table=True):
    __tablename__ = "intervention_links"
    __table_args__ = (
        CheckConstraint(
            "link_type IN ('ORIGIN','EVIDENCE','RELATED','LEGACY_CASE')",
            name="ck_intervention_links_type",
        ),
        UniqueConstraint(
            "intervention_id",
            "link_type",
            "entity_type",
            "entity_id",
            name="uq_intervention_links_identity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    intervention_id: UUID = Field(index=True)
    link_type: str = Field(max_length=30)
    entity_type: str = Field(max_length=100)
    entity_id: UUID
    created_by_user_id: UUID
    created_at: datetime = Field(default_factory=utcnow)


class InterventionAction(SQLModel, table=True):
    __tablename__ = "intervention_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('OPEN','ACKNOWLEDGED','IN_PROGRESS','COMPLETED','CANCELLED','OVERDUE')",
            name="ck_intervention_actions_status",
        ),
        CheckConstraint(
            "(status <> 'COMPLETED') OR "
            "(completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL)",
            name="ck_intervention_actions_completed_requires_actor",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    intervention_id: UUID = Field(index=True)

    action_type: str = Field(default="REVIEW", max_length=40)
    title: str = Field(max_length=240)
    description: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="OPEN", max_length=30)

    assigned_role_code: str | None = Field(default=None, max_length=60)
    assigned_user_id: UUID | None = Field(default=None, index=True)
    due_at: datetime | None = Field(default=None, index=True)

    acknowledged_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    completion_note: str | None = Field(default=None, max_length=2000)

    created_by_user_id: UUID
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class InterventionFollowUp(SQLModel, table=True):
    __tablename__ = "intervention_followups"
    __table_args__ = (
        CheckConstraint(
            "followup_type IN "
            "('MEETING','PHONE_CALL','FAMILY_CONTACT','STUDENT_CONVERSATION',"
            "'TEACHER_REVIEW','ACADEMIC_REVIEW','ATTENDANCE_REVIEW',"
            "'PSYCHOLOGY_SESSION','REFERRAL','OTHER')",
            name="ck_intervention_followups_type",
        ),
        CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_intervention_followups_sensitivity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    intervention_id: UUID = Field(index=True)

    followup_type: str = Field(max_length=50)
    sensitivity: str = Field(default="GENERAL", max_length=20)
    note: str = Field(max_length=4000)
    observed_at: datetime

    created_by_user_id: UUID
    created_at: datetime = Field(default_factory=utcnow)


class InterventionSuggestion(SQLModel, table=True):
    __tablename__ = "intervention_suggestions"
    __table_args__ = (
        CheckConstraint(
            "rule_version >= 1",
            name="ck_intervention_suggestions_rule_version",
        ),
        CheckConstraint(
            "generation_mode = 'RULE_ENGINE'",
            name="ck_intervention_suggestions_generation_mode",
        ),
        CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_intervention_suggestions_severity",
        ),
        CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_intervention_suggestions_sensitivity",
        ),
        CheckConstraint(
            "status IN ('PENDING','ACCEPTED','DISMISSED','EXPIRED')",
            name="ck_intervention_suggestions_status",
        ),
        Index(
            "uq_intervention_suggestions_pending_dedupe",
            "institution_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    section_id: UUID | None = Field(default=None, index=True)

    rule_key: str = Field(max_length=80)
    rule_version: int = Field(default=1)
    generation_mode: str = Field(default="RULE_ENGINE", max_length=30)
    dedupe_key: str = Field(max_length=180)

    recommended_intervention_type: str = Field(max_length=60)
    severity: str = Field(max_length=20)
    sensitivity: str = Field(default="GENERAL", max_length=20)
    title: str = Field(max_length=240)
    rationale_summary: str = Field(max_length=1200)
    status: str = Field(default="PENDING", max_length=20)

    generated_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    reviewed_at: datetime | None = None
    reviewed_by_user_id: UUID | None = None
    review_note: str | None = Field(default=None, max_length=1000)
    accepted_intervention_id: UUID | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class InterventionSuggestionEvidence(SQLModel, table=True):
    __tablename__ = "intervention_suggestion_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN "
            "('INTELLIGENCE_SIGNAL','TIMELINE_ENTRY','EVENT_LEDGER')",
            name="ck_intervention_suggestion_evidence_type",
        ),
        UniqueConstraint(
            "suggestion_id",
            "evidence_type",
            "evidence_id",
            name="uq_intervention_suggestion_evidence_identity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    suggestion_id: UUID = Field(index=True)
    evidence_type: str = Field(max_length=40)
    evidence_id: UUID
    created_at: datetime = Field(default_factory=utcnow)
