from app.main import app
from app.modules.intelligence.service import _severity
from app.modules.m4_events import M4_EVENT_NAMES


def test_m4_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/intelligence/rector/overview",
        "/api/v1/intelligence/rector/sections",
        "/api/v1/intelligence/rector/trends/attendance",
        "/api/v1/intelligence/rector/trends/academic",
        "/api/v1/intelligence/signals",
        "/api/v1/intelligence/signals/refresh",
        "/api/v1/intelligence/signals/{signal_id}/resolve",
    }
    assert expected.issubset(paths)


def test_signal_severity_rules_are_explainable() -> None:
    assert _severity("ACADEMIC_RISK", 45.0, 70.0) == "HIGH"
    assert _severity("ACADEMIC_RISK", 65.0, 70.0) == "MEDIUM"
    assert _severity("ATTENDANCE_RISK", 40.0, 20.0) == "HIGH"
    assert _severity("REPEATED_LATE", 3.0, 3.0) == "MEDIUM"


def test_m4_events_are_unique_and_namespaced() -> None:
    assert len(M4_EVENT_NAMES) == 5
    assert all("." in event for event in M4_EVENT_NAMES)
