from pathlib import Path

import pytest
from fastapi import HTTPException

from app.modules.interventions.schemas import (
    InterventionAssign,
    InterventionCancel,
    InterventionClose,
    InterventionCreate,
    InterventionResolve,
    InterventionTransition,
)
from app.modules.interventions.service import _validate_transition

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app" / "modules" / "interventions" / "service.py"


def test_m21_b2_create_schema_defaults():
    payload = InterventionCreate(
        student_profile_id="00000000-0000-0000-0000-000000000001",
        intervention_type="ACADEMIC_SUPPORT",
        title="Support plan",
        reason="Structured reason",
    )
    assert payload.severity == "MEDIUM"
    assert payload.sensitivity == "GENERAL"
    assert payload.origin_type == "HUMAN"


def test_m21_b2_assignment_requires_target():
    with pytest.raises(ValueError):
        InterventionAssign()


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("OPEN", "IN_PROGRESS"),
        ("IN_PROGRESS", "MONITORING"),
        ("MONITORING", "IN_PROGRESS"),
        ("RESOLVED", "IN_PROGRESS"),
        ("RESOLVED", "MONITORING"),
    ],
)
def test_m21_b2_allowed_human_transitions(current, target):
    _validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("OPEN", "MONITORING"),
        ("OPEN", "CLOSED"),
        ("OPEN", "RESOLVED"),
        ("IN_PROGRESS", "CLOSED"),
        ("MONITORING", "CLOSED"),
        ("CLOSED", "IN_PROGRESS"),
        ("CANCELLED", "IN_PROGRESS"),
    ],
)
def test_m21_b2_invalid_transitions_rejected(current, target):
    with pytest.raises(HTTPException) as exc:
        _validate_transition(current, target)
    assert exc.value.status_code == 409


def test_m21_b2_transition_schema_excludes_terminal_states():
    for status in ("RESOLVED", "CLOSED", "CANCELLED", "OPEN"):
        with pytest.raises(ValueError):
            InterventionTransition(status=status)


def test_m21_b2_outcome_schemas_require_structured_outcome():
    resolved = InterventionResolve(
        outcome_type="IMPROVED",
        outcome_summary="Structured summary",
    )
    closed = InterventionClose(
        outcome_type="STABLE",
        outcome_summary="Structured closure summary",
    )
    assert resolved.outcome_type == "IMPROVED"
    assert closed.outcome_type == "STABLE"


def test_m21_b2_cancel_requires_reason():
    with pytest.raises(ValueError):
        InterventionCancel(cancellation_reason="")


def test_m21_b2_canonical_event_types_present():
    src = SERVICE.read_text(encoding="utf-8")
    for event_type in (
        "student.intervention.opened",
        "student.intervention.assigned",
        "student.intervention.status_changed",
        "student.intervention.resolved",
        "student.intervention.closed",
        "student.intervention.cancelled",
    ):
        assert event_type in src


def test_m21_b2_canonical_payload_excludes_sensitive_free_text():
    src = SERVICE.read_text(encoding="utf-8")
    safe_payload = src.split(
        "def _safe_event_payload",
        maxsplit=1,
    )[1].split("def _emit", maxsplit=1)[0]
    assert '"reason"' not in safe_payload
    assert '"objective"' not in safe_payload
    assert '"outcome_summary"' not in safe_payload
    assert '"student_profile_id"' in safe_payload
    assert '"intervention_id"' in safe_payload
    assert '"sensitivity"' in safe_payload


def test_m21_b2_event_and_mutation_share_commit_boundary():
    src = SERVICE.read_text(encoding="utf-8")
    for function_name in (
        "create_intervention",
        "assign_intervention",
        "transition_intervention",
        "resolve_intervention",
        "close_intervention",
        "cancel_intervention",
    ):
        body = src.split(f"def {function_name}", maxsplit=1)[1]
        body = body.split("\ndef ", maxsplit=1)[0]
        assert "_emit(" in body
        assert "session.commit()" in body
        assert body.index("_emit(") < body.index("session.commit()")


def test_m21_b2_human_authorization_metadata():
    src = SERVICE.read_text(encoding="utf-8")
    assert 'metadata={"human_authorized": True}' in src


def test_m21_b2_permission_boundary_in_service():
    src = SERVICE.read_text(encoding="utf-8")
    assert '"intervention.create"' in src
    assert '"intervention.assign"' in src
    assert '"intervention.update"' in src
    assert '"intervention.resolve"' in src
    assert '"intervention.close"' in src


def test_m21_b2_direct_open_to_closed_is_not_implemented():
    src = SERVICE.read_text(encoding="utf-8")
    assert 'if entity.status != "RESOLVED"' in src
    assert "Only RESOLVED interventions may be closed" in src


def test_m21_b2_terminal_states_are_immutable_through_workflow():
    src = SERVICE.read_text(encoding="utf-8")
    assert '_TERMINAL_STATES = {"CLOSED", "CANCELLED"}' in src