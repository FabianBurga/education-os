from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.student_timeline.projector import (
    EVENT_SPECS,
    PROJECTION_KEY,
    TimelineProjectionError,
    map_ledger_event,
)

NOW = datetime.now(UTC)


def _mapped(event_type: str, payload: dict, *, event_version: int = 1):
    return map_ledger_event(
        ledger_event_id=uuid4(),
        ledger_position=1,
        organization_id=uuid4(),
        institution_id=uuid4(),
        event_type=event_type,
        event_version=event_version,
        aggregate_type="test",
        aggregate_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=None,
        causation_id=None,
        payload={"student_profile_id": str(uuid4()), **payload},
        occurred_at=NOW,
        recorded_at=NOW,
    )


@pytest.mark.parametrize(
    ("event_type", "category"),
    [
        ("student.enrollment.created", "ENROLLMENT"),
        ("student.enrollment.status_changed", "ENROLLMENT"),
        ("student.attendance.recorded", "ATTENDANCE"),
        ("student.attendance.updated", "ATTENDANCE"),
        ("student.grade.recorded", "ACADEMIC"),
        ("student.grade.updated", "ACADEMIC"),
        ("student.signal.opened", "SIGNAL"),
        ("student.signal.closed", "SIGNAL"),
        ("student.signal.resolved", "SIGNAL"),
    ],
)
def test_all_m21_a2_events_are_supported(event_type: str, category: str):
    entry = _mapped(event_type, {})
    assert entry is not None
    assert entry["category"] == category
    assert entry["sensitivity"] == "GENERAL"


def test_projection_key_is_versioned():
    assert PROJECTION_KEY == "m21.student_timeline.v1"


def test_unknown_events_are_skipped_safely():
    entry = _mapped("unrelated.legacy.event", {"anything": "value"})
    assert entry is None


def test_supported_event_requires_student_profile_id():
    with pytest.raises(TimelineProjectionError):
        map_ledger_event(
            ledger_event_id=uuid4(),
            ledger_position=1,
            organization_id=uuid4(),
            institution_id=uuid4(),
            event_type="student.attendance.recorded",
            event_version=1,
            aggregate_type="attendance_record",
            aggregate_id=uuid4(),
            actor_user_id=None,
            correlation_id=None,
            causation_id=None,
            payload={},
            occurred_at=NOW,
            recorded_at=NOW,
        )


def test_future_version_is_not_silently_projected():
    with pytest.raises(TimelineProjectionError):
        _mapped(
            "student.grade.recorded",
            {"score": 9.5},
            event_version=2,
        )


def test_attendance_note_is_not_copied_to_timeline():
    entry = _mapped(
        "student.attendance.recorded",
        {
            "class_session_id": str(uuid4()),
            "attendance_code_id": str(uuid4()),
            "minutes_late": 4,
            "note": "private teacher note",
        },
    )
    assert entry is not None
    assert "note" not in entry["context_json"]
    assert entry["summary"] is None


def test_grade_feedback_is_not_copied_to_timeline():
    entry = _mapped(
        "student.grade.updated",
        {
            "assessment_id": str(uuid4()),
            "score": 8.5,
            "feedback": "private feedback",
        },
    )
    assert entry is not None
    assert "feedback" not in entry["context_json"]


@pytest.mark.parametrize(
    "event_type",
    ["student.signal.closed", "student.signal.resolved"],
)
def test_signal_resolution_note_is_not_copied(event_type: str):
    entry = _mapped(
        event_type,
        {
            "signal_type": "ACADEMIC_RISK",
            "severity": "HIGH",
            "closure_type": "HUMAN",
            "resolution_note": "sensitive free text",
        },
    )
    assert entry is not None
    assert "resolution_note" not in entry["context_json"]
    assert entry["summary"] is None


def test_signal_opened_can_keep_bounded_generated_summary():
    entry = _mapped(
        "student.signal.opened",
        {
            "signal_type": "ATTENDANCE_RISK",
            "severity": "HIGH",
            "summary": "Attendance risk detected.",
        },
    )
    assert entry is not None
    assert entry["summary"] == "Attendance risk detected."
    assert entry["importance"] == "HIGH"


def test_medium_signal_maps_to_normal_timeline_importance():
    entry = _mapped(
        "student.signal.opened",
        {
            "signal_type": "REPEATED_LATE",
            "severity": "MEDIUM",
        },
    )
    assert entry is not None
    assert entry["importance"] == "NORMAL"


def test_projector_contract_contains_idempotency_and_checkpoint():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "student_timeline"
        / "projector.py"
    ).read_text(encoding="utf-8")
    assert len(EVENT_SPECS) == 23
    assert "ON CONFLICT (institution_id, ledger_event_id) DO NOTHING" in source
    assert "projection_checkpoints" in source
    assert "m21_student_timeline_source_events" in source
    assert "FROM event_ledger" not in source
