from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

POLICY_KEY = "institutional_intelligence"
POLICY_SOURCE_BUILTIN = "BUILTIN_DEFAULT"
POLICY_SOURCE_CONTROL_PLANE = "CONTROL_PLANE"


class IntelligencePolicyError(ValueError):
    """Raised when an enabled M22 policy document is invalid."""


@dataclass(frozen=True, slots=True)
class AttendancePolicy:
    absence_threshold_percent: float = 20.0
    minimum_records: int = 5
    late_count_threshold: int = 3


@dataclass(frozen=True, slots=True)
class AcademicPolicy:
    average_threshold_percent: float = 70.0
    minimum_graded_records: int = 2
    missing_work_threshold: int = 3


@dataclass(frozen=True, slots=True)
class InterventionPolicy:
    followup_overdue_calendar_days: int = 7


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    minimum_cohort_size: int = 5


@dataclass(frozen=True, slots=True)
class PersistencePolicy:
    minimum_consecutive_snapshots: int = 2


@dataclass(frozen=True, slots=True)
class ResolvedIntelligencePolicy:
    policy_source: str
    policy_key: str
    policy_version: int
    control_revision: int | None
    attendance: AttendancePolicy
    academic: AcademicPolicy
    intervention: InterventionPolicy
    privacy: PrivacyPolicy
    persistence: PersistencePolicy


def default_intelligence_policy() -> ResolvedIntelligencePolicy:
    return ResolvedIntelligencePolicy(
        policy_source=POLICY_SOURCE_BUILTIN,
        policy_key=POLICY_KEY,
        policy_version=1,
        control_revision=None,
        attendance=AttendancePolicy(),
        academic=AcademicPolicy(),
        intervention=InterventionPolicy(),
        privacy=PrivacyPolicy(),
        persistence=PersistencePolicy(),
    )


def _section(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise IntelligencePolicyError(f"{key} must be an object")
    return value


def _number(
    section: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float | None = None,
) -> float:
    raw = section.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise IntelligencePolicyError(f"{key} must be numeric")
    value = float(raw)
    if value < minimum:
        raise IntelligencePolicyError(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise IntelligencePolicyError(f"{key} must be <= {maximum}")
    return value


def _integer(
    section: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
) -> int:
    raw = section.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise IntelligencePolicyError(f"{key} must be an integer")
    if raw < minimum:
        raise IntelligencePolicyError(f"{key} must be >= {minimum}")
    return raw


def policy_from_document(
    document: dict[str, Any] | None,
    *,
    source: str,
    version: int,
    control_revision: int | None,
) -> ResolvedIntelligencePolicy:
    if source not in {
        POLICY_SOURCE_BUILTIN,
        POLICY_SOURCE_CONTROL_PLANE,
    }:
        raise IntelligencePolicyError(f"unsupported policy source: {source}")
    if version < 1:
        raise IntelligencePolicyError("policy version must be >= 1")
    if source == POLICY_SOURCE_BUILTIN and control_revision is not None:
        raise IntelligencePolicyError(
            "BUILTIN_DEFAULT must not carry a control revision"
        )
    if source == POLICY_SOURCE_CONTROL_PLANE and (
        control_revision is None or control_revision <= 0
    ):
        raise IntelligencePolicyError(
            "CONTROL_PLANE requires a positive control revision"
        )

    document = dict(document or {})
    defaults = default_intelligence_policy()

    attendance = _section(document, "attendance")
    academic = _section(document, "academic")
    intervention = _section(document, "intervention")
    privacy = _section(document, "privacy")
    persistence = _section(document, "persistence")

    return ResolvedIntelligencePolicy(
        policy_source=source,
        policy_key=POLICY_KEY,
        policy_version=version,
        control_revision=control_revision,
        attendance=AttendancePolicy(
            absence_threshold_percent=_number(
                attendance,
                "absence_threshold_percent",
                defaults.attendance.absence_threshold_percent,
                minimum=0.0,
                maximum=100.0,
            ),
            minimum_records=_integer(
                attendance,
                "minimum_records",
                defaults.attendance.minimum_records,
                minimum=1,
            ),
            late_count_threshold=_integer(
                attendance,
                "late_count_threshold",
                defaults.attendance.late_count_threshold,
                minimum=1,
            ),
        ),
        academic=AcademicPolicy(
            average_threshold_percent=_number(
                academic,
                "average_threshold_percent",
                defaults.academic.average_threshold_percent,
                minimum=0.0,
                maximum=100.0,
            ),
            minimum_graded_records=_integer(
                academic,
                "minimum_graded_records",
                defaults.academic.minimum_graded_records,
                minimum=1,
            ),
            missing_work_threshold=_integer(
                academic,
                "missing_work_threshold",
                defaults.academic.missing_work_threshold,
                minimum=1,
            ),
        ),
        intervention=InterventionPolicy(
            followup_overdue_calendar_days=_integer(
                intervention,
                "followup_overdue_calendar_days",
                defaults.intervention.followup_overdue_calendar_days,
                minimum=1,
            ),
        ),
        privacy=PrivacyPolicy(
            minimum_cohort_size=_integer(
                privacy,
                "minimum_cohort_size",
                defaults.privacy.minimum_cohort_size,
                minimum=2,
            ),
        ),
        persistence=PersistencePolicy(
            minimum_consecutive_snapshots=_integer(
                persistence,
                "minimum_consecutive_snapshots",
                defaults.persistence.minimum_consecutive_snapshots,
                minimum=2,
            ),
        ),
    )


def resolve_intelligence_policy(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
) -> ResolvedIntelligencePolicy:
    row = session.exec(
        text(
            """
            SELECT
                p.enabled,
                p.policy_json,
                p.policy_version,
                latest.revision
            FROM institution_policy_controls p
            LEFT JOIN LATERAL (
                SELECT c.revision
                FROM institution_control_changes c
                WHERE c.organization_id = p.organization_id
                  AND c.institution_id = p.institution_id
                  AND c.change_type = 'POLICY'
                  AND c.subject_key = p.policy_key
                ORDER BY c.revision DESC
                LIMIT 1
            ) latest ON true
            WHERE p.organization_id = CAST(:organization_id AS uuid)
              AND p.institution_id = CAST(:institution_id AS uuid)
              AND p.policy_key = :policy_key
            """
        ),
        params={
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "policy_key": POLICY_KEY,
        },
    ).first()

    if row is None or not bool(row[0]):
        return default_intelligence_policy()

    revision = int(row[3]) if row[3] is not None else None
    return policy_from_document(
        dict(row[1] or {}),
        source=POLICY_SOURCE_CONTROL_PLANE,
        version=int(row[2]),
        control_revision=revision,
    )
