from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

PROJECTION_KEY = "m21.student_timeline.v1"


class TimelineProjectionError(ValueError):
    """Raised when a supported ledger event violates the M21 projection contract."""


@dataclass(frozen=True, slots=True)
class TimelineEventSpec:
    category: str
    title: str
    sensitivity: str = "GENERAL"


@dataclass(frozen=True, slots=True)
class TimelineProjectionStats:
    scanned: int
    inserted: int
    skipped: int
    last_position: int


EVENT_SPECS: dict[str, TimelineEventSpec] = {
    "student.enrollment.created": TimelineEventSpec(
        category="ENROLLMENT",
        title="Enrollment created",
    ),
    "student.enrollment.status_changed": TimelineEventSpec(
        category="ENROLLMENT",
        title="Enrollment status changed",
    ),
    "student.attendance.recorded": TimelineEventSpec(
        category="ATTENDANCE",
        title="Attendance recorded",
    ),
    "student.attendance.updated": TimelineEventSpec(
        category="ATTENDANCE",
        title="Attendance updated",
    ),
    "student.grade.recorded": TimelineEventSpec(
        category="ACADEMIC",
        title="Grade recorded",
    ),
    "student.grade.updated": TimelineEventSpec(
        category="ACADEMIC",
        title="Grade updated",
    ),
    "student.signal.opened": TimelineEventSpec(
        category="SIGNAL",
        title="Student signal opened",
    ),
    "student.signal.closed": TimelineEventSpec(
        category="SIGNAL",
        title="Student signal closed",
    ),
    "student.signal.resolved": TimelineEventSpec(
        category="SIGNAL",
        title="Student signal resolved",
    ),
    "student.intervention.opened": TimelineEventSpec(
        category="INTERVENTION",
        title="Intervention opened",
    ),
    "student.intervention.assigned": TimelineEventSpec(
        category="INTERVENTION",
        title="Intervention assigned",
    ),
    "student.intervention.status_changed": TimelineEventSpec(
        category="INTERVENTION",
        title="Intervention status changed",
    ),
    "student.intervention.cancelled": TimelineEventSpec(
        category="INTERVENTION",
        title="Intervention cancelled",
    ),
    "student.intervention.resolved": TimelineEventSpec(
        category="OUTCOME",
        title="Intervention resolved",
    ),
    "student.intervention.closed": TimelineEventSpec(
        category="OUTCOME",
        title="Intervention closed",
    ),
    "student.intervention.reopened": TimelineEventSpec(
        category="INTERVENTION",
        title="Intervention reopened",
    ),
    "student.intervention.action_created": TimelineEventSpec(
        category="ACTION",
        title="Intervention action created",
    ),
    "student.intervention.action_assigned": TimelineEventSpec(
        category="ACTION",
        title="Intervention action assigned",
    ),
    "student.intervention.action_acknowledged": TimelineEventSpec(
        category="ACTION",
        title="Intervention action acknowledged",
    ),
    "student.intervention.action_started": TimelineEventSpec(
        category="ACTION",
        title="Intervention action started",
    ),
    "student.intervention.action_completed": TimelineEventSpec(
        category="ACTION",
        title="Intervention action completed",
    ),
    "student.intervention.action_cancelled": TimelineEventSpec(
        category="ACTION",
        title="Intervention action cancelled",
    ),
    "student.intervention.followup_recorded": TimelineEventSpec(
        category="FOLLOW_UP",
        title="Intervention follow-up recorded",
    ),
}

SAFE_CONTEXT_KEYS: dict[str, tuple[str, ...]] = {
    "student.enrollment.created": (
        "academic_period_id",
        "campus_id",
        "status",
        "enrolled_on",
    ),
    "student.enrollment.status_changed": (
        "academic_period_id",
        "previous_status",
        "status",
        "withdrawn_on",
    ),
    "student.attendance.recorded": (
        "student_section_assignment_id",
        "class_session_id",
        "section_id",
        "attendance_code_id",
        "minutes_late",
    ),
    "student.attendance.updated": (
        "student_section_assignment_id",
        "class_session_id",
        "section_id",
        "attendance_code_id",
        "minutes_late",
    ),
    "student.grade.recorded": (
        "student_section_assignment_id",
        "assessment_id",
        "section_id",
        "status",
        "score",
    ),
    "student.grade.updated": (
        "student_section_assignment_id",
        "assessment_id",
        "section_id",
        "status",
        "score",
    ),
    "student.signal.opened": (
        "academic_period_id",
        "section_id",
        "signal_type",
        "severity",
        "metric_value",
        "threshold_value",
    ),
    "student.signal.closed": (
        "academic_period_id",
        "section_id",
        "signal_type",
        "severity",
        "closure_type",
    ),
    "student.signal.resolved": (
        "academic_period_id",
        "section_id",
        "signal_type",
        "severity",
        "closure_type",
    ),
    "student.intervention.opened": (
        "intervention_id",
        "intervention_type",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
    ),
    "student.intervention.assigned": (
        "intervention_id",
        "intervention_type",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
    ),
    "student.intervention.status_changed": (
        "intervention_id",
        "intervention_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
    ),
    "student.intervention.cancelled": (
        "intervention_id",
        "intervention_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
        "cancellation_reason_recorded",
    ),
    "student.intervention.resolved": (
        "intervention_id",
        "intervention_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
        "outcome_type",
    ),
    "student.intervention.closed": (
        "intervention_id",
        "intervention_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
        "outcome_type",
    ),
    "student.intervention.reopened": (
        "intervention_id",
        "intervention_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "origin_type",
        "assigned_role_code",
        "assigned_user_id",
        "academic_period_id",
        "section_id",
        "target_at",
    ),
    "student.intervention.action_created": (
        "intervention_id",
        "action_id",
        "action_type",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
    ),
    "student.intervention.action_assigned": (
        "intervention_id",
        "action_id",
        "action_type",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
    ),
    "student.intervention.action_acknowledged": (
        "intervention_id",
        "action_id",
        "action_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
    ),
    "student.intervention.action_started": (
        "intervention_id",
        "action_id",
        "action_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
    ),
    "student.intervention.action_completed": (
        "intervention_id",
        "action_id",
        "action_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
        "completion_note_recorded",
    ),
    "student.intervention.action_cancelled": (
        "intervention_id",
        "action_id",
        "action_type",
        "previous_status",
        "status",
        "severity",
        "sensitivity",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
    ),
    "student.intervention.followup_recorded": (
        "intervention_id",
        "followup_id",
        "followup_type",
        "severity",
        "sensitivity",
        "observed_at",
    ),
}


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, 5000))


def _required_student_profile_id(payload: dict[str, Any], event_type: str) -> UUID:
    raw = payload.get("student_profile_id")
    if not raw:
        raise TimelineProjectionError(
            f"{event_type} is missing required student_profile_id"
        )
    try:
        return UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise TimelineProjectionError(
            f"{event_type} has invalid student_profile_id"
        ) from exc


def _importance(event_type: str, payload: dict[str, Any]) -> str:
    if event_type.startswith(("student.signal.", "student.intervention.")):
        severity = str(payload.get("severity") or "").upper()
        if severity == "CRITICAL":
            return "CRITICAL"
        if severity == "HIGH":
            return "HIGH"
        if event_type.startswith("student.intervention.") and severity == "LOW":
            return "LOW"
    return "NORMAL"


def _sensitivity(
    event_type: str,
    payload: dict[str, Any],
    spec: TimelineEventSpec,
) -> str:
    if not event_type.startswith("student.intervention."):
        return spec.sensitivity

    value = str(payload.get("sensitivity") or "").upper()
    if value not in {"GENERAL", "RESTRICTED", "CONFIDENTIAL"}:
        raise TimelineProjectionError(
            f"{event_type} has invalid or missing sensitivity"
        )
    return value


def _safe_summary(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type != "student.signal.opened":
        return None
    value = payload.get("summary")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:1200] if value else None


def _safe_context(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    keys = SAFE_CONTEXT_KEYS[event_type]
    return {
        key: payload[key]
        for key in keys
        if key in payload and payload[key] is not None
    }


def map_ledger_event(
    *,
    ledger_event_id: UUID,
    ledger_position: int,
    organization_id: UUID,
    institution_id: UUID,
    event_type: str,
    event_version: int,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_user_id: UUID | None,
    correlation_id: UUID | None,
    causation_id: UUID | None,
    payload: dict[str, Any],
    occurred_at: Any,
    recorded_at: Any,
) -> dict[str, Any] | None:
    """Map one supported canonical ledger event to the timeline read model."""
    spec = EVENT_SPECS.get(event_type)
    if spec is None:
        return None

    if event_version != 1:
        raise TimelineProjectionError(
            f"{event_type} event_version={event_version} is not supported"
        )
    if ledger_position <= 0:
        raise TimelineProjectionError(
            f"{event_type} has invalid ledger position {ledger_position}"
        )
    if not isinstance(payload, dict):
        raise TimelineProjectionError(
            f"{event_type} payload must be an object"
        )

    student_profile_id = _required_student_profile_id(payload, event_type)

    return {
        "id": uuid4(),
        "organization_id": organization_id,
        "institution_id": institution_id,
        "student_profile_id": student_profile_id,
        "ledger_event_id": ledger_event_id,
        "ledger_position": ledger_position,
        "event_type": event_type,
        "event_version": event_version,
        "category": spec.category,
        "importance": _importance(event_type, payload),
        "sensitivity": _sensitivity(event_type, payload, spec),
        "title": spec.title,
        "summary": _safe_summary(event_type, payload),
        "source_aggregate_type": aggregate_type,
        "source_aggregate_id": aggregate_id,
        "actor_user_id": actor_user_id,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "context_json": _safe_context(event_type, payload),
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
    }


def _checkpoint(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
) -> tuple[UUID, int, int]:
    checkpoint_id = uuid4()
    session.exec(
        text(
            """
            INSERT INTO projection_checkpoints (
                id,
                organization_id,
                institution_id,
                projection_key,
                last_position,
                processed_count,
                updated_at
            )
            VALUES (
                CAST(:id AS uuid),
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :projection_key,
                0,
                0,
                NOW()
            )
            ON CONFLICT (institution_id, projection_key) DO NOTHING
            """
        ),
        params={
            "id": str(checkpoint_id),
            "organization_id": str(organization_id),
            "institution_id": str(institution_id),
            "projection_key": PROJECTION_KEY,
        },
    )
    row = session.exec(
        text(
            """
            SELECT id, last_position, processed_count
            FROM projection_checkpoints
            WHERE institution_id = CAST(:institution_id AS uuid)
              AND projection_key = :projection_key
            """
        ),
        params={
            "institution_id": str(institution_id),
            "projection_key": PROJECTION_KEY,
        },
    ).one()
    return row[0], int(row[1]), int(row[2])


def project_student_timeline(
    session: Session,
    *,
    organization_id: UUID,
    institution_id: UUID,
    limit: int = 1000,
) -> TimelineProjectionStats:
    """Advance the M21 timeline read model from the immutable M18 ledger.

    The function does not commit. The caller owns transaction boundaries.
    Unknown event types are skipped safely while still advancing the checkpoint.
    Supported malformed events raise TimelineProjectionError and must not be
    silently skipped.
    """
    checkpoint_id, last_position, processed_count = _checkpoint(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
    )

    rows = session.exec(
        text(
            """
            SELECT
                id,
                ledger_position,
                organization_id,
                institution_id,
                event_type,
                event_version,
                aggregate_type,
                aggregate_id,
                actor_user_id,
                correlation_id,
                causation_id,
                payload_json,
                occurred_at,
                recorded_at
            FROM m21_student_timeline_source_events(
                CAST(:organization_id AS uuid),
                CAST(:institution_id AS uuid),
                :last_position,
                :limit
            )
            ORDER BY ledger_position
            """
        ),
        params={
            "institution_id": str(institution_id),
            "organization_id": str(organization_id),
            "last_position": last_position,
            "limit": _bounded_limit(limit),
        },
    ).all()

    if not rows:
        return TimelineProjectionStats(
            scanned=0,
            inserted=0,
            skipped=0,
            last_position=last_position,
        )

    mapped: list[dict[str, Any]] = []
    skipped = 0

    for row in rows:
        payload = row[11]
        if not isinstance(payload, dict):
            raise TimelineProjectionError(
                f"{row[4]} payload_json is not an object"
            )

        entry = map_ledger_event(
            ledger_event_id=row[0],
            ledger_position=int(row[1]),
            organization_id=row[2],
            institution_id=row[3],
            event_type=str(row[4]),
            event_version=int(row[5]),
            aggregate_type=str(row[6]),
            aggregate_id=row[7],
            actor_user_id=row[8],
            correlation_id=row[9],
            causation_id=row[10],
            payload=payload,
            occurred_at=row[12],
            recorded_at=row[13],
        )
        if entry is None:
            skipped += 1
        else:
            mapped.append(entry)

    inserted = 0
    for entry in mapped:
        result = session.exec(
            text(
                """
                INSERT INTO student_timeline_entries (
                    id,
                    organization_id,
                    institution_id,
                    student_profile_id,
                    ledger_event_id,
                    ledger_position,
                    event_type,
                    event_version,
                    category,
                    importance,
                    sensitivity,
                    title,
                    summary,
                    source_aggregate_type,
                    source_aggregate_id,
                    actor_user_id,
                    correlation_id,
                    causation_id,
                    context_json,
                    occurred_at,
                    recorded_at,
                    projected_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:organization_id AS uuid),
                    CAST(:institution_id AS uuid),
                    CAST(:student_profile_id AS uuid),
                    CAST(:ledger_event_id AS uuid),
                    :ledger_position,
                    :event_type,
                    :event_version,
                    :category,
                    :importance,
                    :sensitivity,
                    :title,
                    :summary,
                    :source_aggregate_type,
                    CAST(:source_aggregate_id AS uuid),
                    CAST(:actor_user_id AS uuid),
                    CAST(:correlation_id AS uuid),
                    CAST(:causation_id AS uuid),
                    CAST(:context_json AS jsonb),
                    :occurred_at,
                    :recorded_at,
                    NOW()
                )
                ON CONFLICT (institution_id, ledger_event_id) DO NOTHING
                RETURNING id
                """
            ),
            params={
                "id": str(entry["id"]),
                "organization_id": str(entry["organization_id"]),
                "institution_id": str(entry["institution_id"]),
                "student_profile_id": str(entry["student_profile_id"]),
                "ledger_event_id": str(entry["ledger_event_id"]),
                "ledger_position": int(entry["ledger_position"]),
                "event_type": entry["event_type"],
                "event_version": int(entry["event_version"]),
                "category": entry["category"],
                "importance": entry["importance"],
                "sensitivity": entry["sensitivity"],
                "title": entry["title"],
                "summary": entry["summary"],
                "source_aggregate_type": entry["source_aggregate_type"],
                "source_aggregate_id": str(entry["source_aggregate_id"]),
                "actor_user_id": (
                    str(entry["actor_user_id"])
                    if entry["actor_user_id"] is not None
                    else None
                ),
                "correlation_id": (
                    str(entry["correlation_id"])
                    if entry["correlation_id"] is not None
                    else None
                ),
                "causation_id": (
                    str(entry["causation_id"])
                    if entry["causation_id"] is not None
                    else None
                ),
                "context_json": __import__("json").dumps(
                    entry["context_json"],
                    separators=(",", ":"),
                ),
                "occurred_at": entry["occurred_at"],
                "recorded_at": entry["recorded_at"],
            },
        ).first()
        if result is not None:
            inserted += 1

    new_last_position = int(rows[-1][1])
    session.exec(
        text(
            """
            UPDATE projection_checkpoints
            SET
                last_position = :last_position,
                processed_count = :processed_count,
                updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
            """
        ),
        params={
            "last_position": new_last_position,
            "processed_count": processed_count + len(rows),
            "id": str(checkpoint_id),
        },
    )

    return TimelineProjectionStats(
        scanned=len(rows),
        inserted=inserted,
        skipped=skipped,
        last_position=new_last_position,
    )