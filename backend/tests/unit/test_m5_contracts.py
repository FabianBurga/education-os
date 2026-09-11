from types import SimpleNamespace

from app.main import app
from app.modules.automation.service import SEVERITY_RANK, rule_matches
from app.modules.m5_events import M5_EVENT_NAMES


def test_m5_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/automation/rules",
        "/api/v1/automation/rules/bootstrap-defaults",
        "/api/v1/automation/engine/run",
        "/api/v1/automation/engine/tick",
        "/api/v1/automation/cases",
        "/api/v1/automation/cases/{case_id}",
        "/api/v1/automation/cases/{case_id}/tasks",
        "/api/v1/automation/cases/{case_id}/timeline",
        "/api/v1/automation/tasks/{task_id}/acknowledge",
        "/api/v1/automation/tasks/{task_id}/complete",
    }
    assert expected.issubset(paths)


def test_severity_rank_is_monotonic() -> None:
    assert SEVERITY_RANK["LOW"] < SEVERITY_RANK["MEDIUM"] < SEVERITY_RANK["HIGH"]


def test_rule_matching_is_explicit() -> None:
    rule = SimpleNamespace(
        is_enabled=True,
        signal_type="ATTENDANCE_RISK",
        minimum_severity="MEDIUM",
    )
    medium_signal = SimpleNamespace(
        signal_type="ATTENDANCE_RISK",
        severity="MEDIUM",
    )
    high_signal = SimpleNamespace(
        signal_type="ATTENDANCE_RISK",
        severity="HIGH",
    )
    wrong_signal = SimpleNamespace(
        signal_type="ACADEMIC_RISK",
        severity="HIGH",
    )

    assert rule_matches(rule, medium_signal)
    assert rule_matches(rule, high_signal)
    assert not rule_matches(rule, wrong_signal)


def test_m5_events_are_unique_and_namespaced() -> None:
    assert len(M5_EVENT_NAMES) == 6
    assert all("." in event for event in M5_EVENT_NAMES)
