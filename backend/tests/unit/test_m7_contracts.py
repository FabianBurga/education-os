from app.api.access import require_staff_access
from app.main import app
from app.modules.m7_events import M7_EVENT_NAMES
from app.modules.operations.router import router as operations_router


def test_m7_operations_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/operations/security-baseline",
        "/api/v1/operations/pilot/data-summary",
        "/api/v1/operations/pilot/readiness/run",
        "/api/v1/operations/pilot/readiness/latest",
    }
    assert expected.issubset(paths)


def test_m7_operations_router_is_staff_protected() -> None:
    calls = {dependency.dependency for dependency in operations_router.dependencies}
    assert require_staff_access in calls


def test_representative_contracts_survive_v1_candidate() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/students",
        "/api/v1/academics/sections",
        "/api/v1/attendance/codes",
        "/api/v1/grades/assessments",
        "/api/v1/intelligence/rector/overview",
        "/api/v1/automation/rules",
        "/api/v1/family-portal/children",
    }
    assert expected.issubset(paths)


def test_m7_events_are_unique_and_namespaced() -> None:
    assert len(M7_EVENT_NAMES) == 5
    assert all("." in event for event in M7_EVENT_NAMES)
