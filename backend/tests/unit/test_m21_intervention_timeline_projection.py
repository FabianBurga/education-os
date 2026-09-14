from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.student_timeline.projector import (
    TimelineProjectionError,
    map_ledger_event,
)

NOW = datetime.now(UTC)

INTERVENTION_EVENTS = (
    ("student.intervention.opened", "INTERVENTION"),
    ("student.intervention.assigned", "INTERVENTION"),
    ("student.intervention.status_changed", "INTERVENTION"),
    ("student.intervention.cancelled", "INTERVENTION"),
    ("student.intervention.resolved", "OUTCOME"),
    ("student.intervention.closed", "OUTCOME"),
)


def _mapped(
    event_type: str,
    *,
    sensitivity: str = "GENERAL",
    severity: str = "MEDIUM",
    extra: dict | None = None,
):
    payload = {
        "student_profile_id": str(uuid4()),
        "intervention_id": str(uuid4()),
        "intervention_type": "ACADEMIC_SUPPORT",
        "status": "IN_PROGRESS",
        "severity": severity,
        "sensitivity": sensitivity,
        "origin_type": "HUMAN",
        "academic_period_id": str(uuid4()),
        "section_id": str(uuid4()),
        "target_at": NOW.isoformat(),
    }
    if extra:
        payload.update(extra)

    return map_ledger_event(
        ledger_event_id=uuid4(),
        ledger_position=101,
        organization_id=uuid4(),
        institution_id=uuid4(),
        event_type=event_type,
        event_version=1,
        aggregate_type="intervention",
        aggregate_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=None,
        causation_id=None,
        payload=payload,
        occurred_at=NOW,
        recorded_at=NOW,
    )


@pytest.mark.parametrize(("event_type", "category"), INTERVENTION_EVENTS)
def test_intervention_events_project_to_expected_categories(event_type, category):
    entry = _mapped(event_type)
    assert entry is not None
    assert entry["category"] == category
    assert entry["source_aggregate_type"] == "intervention"


@pytest.mark.parametrize(
    "sensitivity",
    ["GENERAL", "RESTRICTED", "CONFIDENTIAL"],
)
def test_intervention_sensitivity_is_preserved(sensitivity):
    entry = _mapped("student.intervention.opened", sensitivity=sensitivity)
    assert entry is not None
    assert entry["sensitivity"] == sensitivity


@pytest.mark.parametrize("bad_value", ["", "PRIVATE", "secret"])
def test_intervention_invalid_sensitivity_is_rejected(bad_value):
    with pytest.raises(TimelineProjectionError):
        _mapped("student.intervention.opened", sensitivity=bad_value)


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("LOW", "LOW"),
        ("MEDIUM", "NORMAL"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
    ],
)
def test_intervention_severity_maps_to_timeline_importance(severity, expected):
    entry = _mapped("student.intervention.opened", severity=severity)
    assert entry is not None
    assert entry["importance"] == expected


def test_intervention_safe_context_keeps_structured_fields():
    intervention_id = str(uuid4())
    entry = _mapped(
        "student.intervention.status_changed",
        extra={
            "intervention_id": intervention_id,
            "previous_status": "OPEN",
            "status": "IN_PROGRESS",
            "assigned_role_code": "TEACHER",
        },
    )
    assert entry is not None
    assert entry["context_json"]["intervention_id"] == intervention_id
    assert entry["context_json"]["previous_status"] == "OPEN"
    assert entry["context_json"]["status"] == "IN_PROGRESS"
    assert entry["context_json"]["assigned_role_code"] == "TEACHER"


@pytest.mark.parametrize("event_type", [item[0] for item in INTERVENTION_EVENTS])
def test_intervention_projection_excludes_sensitive_free_text(event_type):
    entry = _mapped(
        event_type,
        extra={
            "reason": "private intervention reason",
            "objective": "private intervention objective",
            "outcome_summary": "private intervention outcome",
            "cancellation_reason": "private cancellation reason",
            "resolution_note": "private resolution note",
        },
    )
    assert entry is not None
    context = entry["context_json"]
    assert "reason" not in context
    assert "objective" not in context
    assert "outcome_summary" not in context
    assert "cancellation_reason" not in context
    assert "resolution_note" not in context
    assert entry["summary"] is None


@pytest.mark.parametrize(
    "event_type",
    ["student.intervention.resolved", "student.intervention.closed"],
)
def test_outcome_events_keep_structured_outcome_type_only(event_type):
    entry = _mapped(
        event_type,
        extra={
            "previous_status": "MONITORING",
            "status": "RESOLVED" if event_type.endswith("resolved") else "CLOSED",
            "outcome_type": "IMPROVED",
            "outcome_summary": "must not leak",
        },
    )
    assert entry is not None
    assert entry["category"] == "OUTCOME"
    assert entry["context_json"]["outcome_type"] == "IMPROVED"
    assert "outcome_summary" not in entry["context_json"]


def test_cancelled_event_keeps_boolean_reason_marker_not_free_text():
    entry = _mapped(
        "student.intervention.cancelled",
        extra={
            "previous_status": "OPEN",
            "status": "CANCELLED",
            "cancellation_reason_recorded": True,
            "cancellation_reason": "must not leak",
        },
    )
    assert entry is not None
    assert entry["context_json"]["cancellation_reason_recorded"] is True
    assert "cancellation_reason" not in entry["context_json"]