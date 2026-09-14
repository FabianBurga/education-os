from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.student_timeline.projector import (
    TimelineProjectionError,
    map_ledger_event,
)

NOW = datetime.now(UTC)

ACTION_EVENTS = (
    "student.intervention.action_created",
    "student.intervention.action_assigned",
    "student.intervention.action_acknowledged",
    "student.intervention.action_started",
    "student.intervention.action_completed",
    "student.intervention.action_cancelled",
)

FOLLOWUP_EVENT = "student.intervention.followup_recorded"


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
        "severity": severity,
        "sensitivity": sensitivity,
    }

    if event_type in ACTION_EVENTS:
        payload.update(
            {
                "action_id": str(uuid4()),
                "action_type": "REVIEW",
                "status": "IN_PROGRESS",
                "assigned_role_code": "ACADEMIC_COORDINATOR",
                "assigned_user_id": str(uuid4()),
                "due_at": NOW.isoformat(),
            }
        )
        aggregate_type = "intervention_action"
    else:
        payload.update(
            {
                "followup_id": str(uuid4()),
                "followup_type": "ACADEMIC_REVIEW",
                "observed_at": NOW.isoformat(),
            }
        )
        aggregate_type = "intervention_followup"

    if extra:
        payload.update(extra)

    return map_ledger_event(
        ledger_event_id=uuid4(),
        ledger_position=501,
        organization_id=uuid4(),
        institution_id=uuid4(),
        event_type=event_type,
        event_version=1,
        aggregate_type=aggregate_type,
        aggregate_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=None,
        causation_id=None,
        payload=payload,
        occurred_at=NOW,
        recorded_at=NOW,
    )


@pytest.mark.parametrize("event_type", ACTION_EVENTS)
def test_action_events_project_to_action_category(event_type):
    entry = _mapped(event_type)
    assert entry is not None
    assert entry["category"] == "ACTION"
    assert entry["source_aggregate_type"] == "intervention_action"
    assert entry["summary"] is None


def test_followup_projects_to_follow_up_category():
    entry = _mapped(FOLLOWUP_EVENT)
    assert entry is not None
    assert entry["category"] == "FOLLOW_UP"
    assert entry["source_aggregate_type"] == "intervention_followup"
    assert entry["summary"] is None


@pytest.mark.parametrize(
    "event_type",
    [*ACTION_EVENTS, FOLLOWUP_EVENT],
)
@pytest.mark.parametrize(
    "sensitivity",
    ["GENERAL", "RESTRICTED", "CONFIDENTIAL"],
)
def test_c3_sensitivity_is_preserved(event_type, sensitivity):
    entry = _mapped(event_type, sensitivity=sensitivity)
    assert entry is not None
    assert entry["sensitivity"] == sensitivity


@pytest.mark.parametrize(
    "event_type",
    [*ACTION_EVENTS, FOLLOWUP_EVENT],
)
@pytest.mark.parametrize("bad_value", ["", "PRIVATE", "secret"])
def test_c3_invalid_sensitivity_is_rejected(event_type, bad_value):
    with pytest.raises(TimelineProjectionError):
        _mapped(event_type, sensitivity=bad_value)


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("LOW", "LOW"),
        ("MEDIUM", "NORMAL"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
    ],
)
def test_action_importance_inherits_intervention_severity(severity, expected):
    entry = _mapped(
        "student.intervention.action_created",
        severity=severity,
    )
    assert entry is not None
    assert entry["importance"] == expected


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("LOW", "LOW"),
        ("MEDIUM", "NORMAL"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
    ],
)
def test_followup_importance_inherits_intervention_severity(severity, expected):
    entry = _mapped(
        FOLLOWUP_EVENT,
        severity=severity,
    )
    assert entry is not None
    assert entry["importance"] == expected


def test_action_safe_context_keeps_structured_fields_only():
    action_id = str(uuid4())
    entry = _mapped(
        "student.intervention.action_completed",
        extra={
            "action_id": action_id,
            "previous_status": "IN_PROGRESS",
            "status": "COMPLETED",
            "completion_note_recorded": True,
            "description": "must not leak",
            "completion_note": "must not leak",
            "title": "must not leak",
        },
    )
    assert entry is not None
    context = entry["context_json"]
    assert context["action_id"] == action_id
    assert context["previous_status"] == "IN_PROGRESS"
    assert context["status"] == "COMPLETED"
    assert context["completion_note_recorded"] is True
    assert "description" not in context
    assert "completion_note" not in context
    assert "title" not in context
    assert entry["summary"] is None


def test_followup_safe_context_excludes_note():
    followup_id = str(uuid4())
    entry = _mapped(
        FOLLOWUP_EVENT,
        sensitivity="RESTRICTED",
        extra={
            "followup_id": followup_id,
            "note": "must not leak",
        },
    )
    assert entry is not None
    context = entry["context_json"]
    assert context["followup_id"] == followup_id
    assert context["followup_type"] == "ACADEMIC_REVIEW"
    assert context["observed_at"] == NOW.isoformat()
    assert "note" not in context
    assert entry["summary"] is None


def test_c3_unknown_event_still_skips_safely():
    entry = _mapped("student.intervention.unknown_c3_event")
    assert entry is None