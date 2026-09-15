from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class IntelligenceSignal(SQLModel, table=True):
    __tablename__ = "intelligence_signals"
    __table_args__ = (
        UniqueConstraint(
            "student_profile_id",
            "academic_period_id",
            "signal_type",
            "status",
            name="uq_intelligence_signal_student_period_type_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    section_id: UUID | None = Field(default=None, index=True)
    student_profile_id: UUID = Field(index=True)
    signal_type: str = Field(max_length=40)
    severity: str = Field(max_length=20)
    metric_value: float
    threshold_value: float
    summary: str = Field(max_length=500)
    status: str = Field(default="OPEN", max_length=20)
    detected_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    resolution_note: str | None = Field(default=None, max_length=1000)
class StudentIntelligenceSnapshot(SQLModel, table=True):
    __tablename__ = "student_intelligence_snapshots"
    __table_args__ = (
        CheckConstraint(
            "overall_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_overall_priority",
        ),
        CheckConstraint(
            "attendance_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_attendance_priority",
        ),
        CheckConstraint(
            "academic_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_academic_priority",
        ),
        CheckConstraint(
            "intervention_priority IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_intelligence_snapshots_intervention_priority",
        ),
        UniqueConstraint(
            "institution_id",
            "student_profile_id",
            "snapshot_date",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            name="uq_student_intelligence_snapshots_identity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    student_profile_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    snapshot_date: date = Field(index=True)
    evaluated_at: datetime = Field(default_factory=utcnow)
    overall_priority: str = Field(max_length=20)
    attendance_priority: str = Field(max_length=20)
    academic_priority: str = Field(max_length=20)
    intervention_priority: str = Field(max_length=20)
    evidence_count: int = 0
    rule_set_version: int = 1
    projection_version: int = 1
    policy_source: str = Field(default="BUILTIN_DEFAULT", max_length=30)
    policy_key: str = Field(
        default="institutional_intelligence",
        max_length=120,
    )
    policy_version: int = 1
    control_revision: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CohortIntelligenceDaily(SQLModel, table=True):
    __tablename__ = "cohort_intelligence_daily"
    __table_args__ = (
        CheckConstraint(
            "cohort_type IN "
            "('INSTITUTION','ACADEMIC_LEVEL','GRADE','SECTION','COURSE')",
            name="ck_cohort_intelligence_daily_type",
        ),
        Index(
            "uq_cohort_intelligence_daily_identity_ref",
            "institution_id",
            "snapshot_date",
            "cohort_type",
            "cohort_ref_id",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            unique=True,
            postgresql_where=text("cohort_ref_id IS NOT NULL"),
        ),
        Index(
            "uq_cohort_intelligence_daily_identity_institution",
            "institution_id",
            "snapshot_date",
            "cohort_type",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            unique=True,
            postgresql_where=text(
                "cohort_type = 'INSTITUTION' "
                "AND cohort_ref_id IS NULL"
            ),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    snapshot_date: date = Field(index=True)
    cohort_type: str = Field(max_length=30)
    cohort_ref_id: UUID | None = Field(default=None)
    student_count: int
    high_priority_count: int | None = None
    medium_priority_count: int | None = None
    attendance_risk_count: int | None = None
    academic_risk_count: int | None = None
    active_intervention_count: int | None = None
    overdue_followup_count: int | None = None
    suppressed: bool = False
    rule_set_version: int = 1
    projection_version: int = 1
    policy_source: str = Field(default="BUILTIN_DEFAULT", max_length=30)
    policy_key: str = Field(
        default="institutional_intelligence",
        max_length=120,
    )
    policy_version: int = 1
    control_revision: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class InstitutionIntelligenceDaily(SQLModel, table=True):
    __tablename__ = "institution_intelligence_daily"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "snapshot_date",
            "rule_set_version",
            "projection_version",
            "policy_source",
            "policy_key",
            "policy_version",
            name="uq_institution_intelligence_daily_identity",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(index=True)
    institution_id: UUID = Field(index=True)
    academic_period_id: UUID | None = Field(default=None, index=True)
    snapshot_date: date = Field(index=True)
    in_scope_student_count: int
    high_priority_count: int
    medium_priority_count: int
    active_intervention_count: int
    interventions_without_action_count: int
    overdue_followup_count: int
    positive_outcome_count: int
    unresolved_outcome_count: int
    rule_set_version: int = 1
    projection_version: int = 1
    policy_source: str = Field(default="BUILTIN_DEFAULT", max_length=30)
    policy_key: str = Field(
        default="institutional_intelligence",
        max_length=120,
    )
    policy_version: int = 1
    control_revision: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
