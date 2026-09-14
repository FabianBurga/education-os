from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.modules.student_timeline.projector import map_ledger_event


def test_m21_c5_service_enforces_active_action_barrier():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert "def _assert_no_active_actions(" in source
    assert 'operation="resolve"' in source
    assert 'operation="close"' in source
    assert "('OPEN','ACKNOWLEDGED','IN_PROGRESS','OVERDUE')" in source


def test_m21_c5_close_must_match_resolved_outcome():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert "def _assert_close_outcome_consistent(" in source
    assert "payload.outcome_type != entity.outcome_type" in source
    assert "payload.outcome_summary != entity.outcome_summary" in source


def test_m21_c5_reopen_has_dedicated_canonical_event():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert 'event_type = "student.intervention.reopened"' in source
    assert "entity.resolved_at = None" in source
    assert "entity.outcome_type = None" in source
    assert "entity.outcome_summary = None" in source
    assert "entity.outcome_recorded_at = None" in source
    assert "entity.outcome_recorded_by_user_id = None" in source


def test_m21_c5_reopened_projects_as_intervention_without_outcome_text():
    now = datetime.now(UTC)
    entry = map_ledger_event(
        ledger_event_id=uuid4(),
        ledger_position=9001,
        organization_id=uuid4(),
        institution_id=uuid4(),
        event_type="student.intervention.reopened",
        event_version=1,
        aggregate_type="intervention",
        aggregate_id=uuid4(),
        actor_user_id=uuid4(),
        correlation_id=None,
        causation_id=None,
        payload={
            "student_profile_id": str(uuid4()),
            "intervention_id": str(uuid4()),
            "intervention_type": "ACADEMIC",
            "previous_status": "RESOLVED",
            "status": "IN_PROGRESS",
            "severity": "HIGH",
            "sensitivity": "GENERAL",
            "origin_type": "HUMAN",
            "outcome_type": None,
            "outcome_summary": "must never project",
        },
        occurred_at=now,
        recorded_at=now,
    )

    assert entry is not None
    assert entry["category"] == "INTERVENTION"
    assert entry["importance"] == "HIGH"
    assert entry["sensitivity"] == "GENERAL"
    assert entry["context_json"]["previous_status"] == "RESOLVED"
    assert entry["context_json"]["status"] == "IN_PROGRESS"
    assert "outcome_type" not in entry["context_json"]
    assert "outcome_summary" not in entry["context_json"]
    assert entry["summary"] is None
