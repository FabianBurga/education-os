from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.interventions.schemas import (
    InterventionActionAssign,
    InterventionActionComplete,
    InterventionActionCreate,
    InterventionActionTransition,
)

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app" / "modules" / "interventions" / "service.py"
SCHEMAS = ROOT / "app" / "modules" / "interventions" / "schemas.py"


def test_m21_c2_action_create_schema():
    payload = InterventionActionCreate(
        title="Review attendance plan",
        assigned_role_code="ACADEMIC_COORDINATOR",
    )
    assert payload.action_type == "REVIEW"
    assert payload.title == "Review attendance plan"


def test_m21_c2_action_assignment_requires_target():
    with pytest.raises(ValidationError):
        InterventionActionAssign()


def test_m21_c2_action_transition_is_human_workflow_only():
    for state in ("ACKNOWLEDGED", "IN_PROGRESS", "CANCELLED"):
        assert InterventionActionTransition(status=state).status == state

    for invalid in ("OPEN", "COMPLETED", "OVERDUE"):
        with pytest.raises(ValidationError):
            InterventionActionTransition(status=invalid)


def test_m21_c2_completion_note_is_bounded():
    assert InterventionActionComplete(completion_note=None).completion_note is None
    with pytest.raises(ValidationError):
        InterventionActionComplete(completion_note="x" * 2001)


def test_m21_c2_followup_schema_contract():
    src = SCHEMAS.read_text(encoding="utf-8")
    assert "class InterventionFollowUpCreate" in src
    assert "PSYCHOLOGY_SESSION" in src
    assert "CONFIDENTIAL" in src
    assert "max_length=4000" in src


def test_m21_c2_service_has_action_workflow_methods():
    src = SERVICE.read_text(encoding="utf-8")
    for function_name in (
        "create_intervention_action",
        "assign_intervention_action",
        "transition_intervention_action",
        "complete_intervention_action",
        "create_intervention_followup",
    ):
        assert f"def {function_name}(" in src


def test_m21_c2_action_transition_graph_blocks_terminal_states():
    src = SERVICE.read_text(encoding="utf-8")
    assert '"COMPLETED": frozenset()' in src
    assert '"CANCELLED": frozenset()' in src
    assert '_ACTION_TERMINAL_STATES = {"COMPLETED", "CANCELLED"}' in src


def test_m21_c2_overdue_is_not_a_human_transition():
    src = SERVICE.read_text(encoding="utf-8")
    transition_body = src.split(
        "def transition_intervention_action", maxsplit=1
    )[1].split(
        "\ndef complete_intervention_action", maxsplit=1
    )[0]
    assert '"OVERDUE"' not in transition_body


def test_m21_c2_canonical_events_are_emitted():
    src = SERVICE.read_text(encoding="utf-8")
    for event_type in (
        "student.intervention.action_created",
        "student.intervention.action_assigned",
        "student.intervention.action_acknowledged",
        "student.intervention.action_started",
        "student.intervention.action_completed",
        "student.intervention.action_cancelled",
        "student.intervention.followup_recorded",
    ):
        assert f'"{event_type}"' in src


def test_m21_c2_canonical_payload_excludes_sensitive_free_text():
    src = SERVICE.read_text(encoding="utf-8")

    action_payload = src.split(
        "def _safe_action_event_payload", maxsplit=1
    )[1].split(
        "\ndef _emit_action_event", maxsplit=1
    )[0]
    assert '"description"' not in action_payload
    assert '"completion_note"' not in action_payload

    followup_payload = src.split(
        "def _emit_followup_event", maxsplit=1
    )[1].split(
        "\ndef _validate_action_transition", maxsplit=1
    )[0]
    assert '"note"' not in followup_payload


def test_m21_c2_followup_sensitivity_cannot_downgrade_parent():
    src = SERVICE.read_text(encoding="utf-8")
    body = src.split("def create_intervention_followup", maxsplit=1)[1]
    assert 'parent.sensitivity == "CONFIDENTIAL"' in body
    assert 'parent.sensitivity == "RESTRICTED"' in body
    assert "sensitivity cannot be lower" in body


def test_m21_c2_permissions_are_explicit():
    src = SERVICE.read_text(encoding="utf-8")
    assert '"intervention.action.manage"' in src
    assert '"intervention.followup.create"' in src