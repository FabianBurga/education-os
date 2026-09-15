from app.api.access import (
    require_coordination_access,
    require_staff_access,
)
from app.api.v1.m1_router import router as m1_router
from app.api.v1.m2_router import router as m2_router
from app.api.v1.m3_router import router as m3_router
from app.api.v1.m4_router import router as m4_router
from app.api.v1.m5_router import router as m5_router
from app.main import app
from app.modules.m6_events import M6_EVENT_NAMES


def _dependency_calls(router):
    return {dependency.dependency for dependency in router.dependencies}


def test_m6_family_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/family-portal/me",
        "/api/v1/family-portal/children",
        "/api/v1/family-portal/children/{student_profile_id}/overview",
        "/api/v1/family-portal/children/{student_profile_id}/attendance",
        "/api/v1/family-portal/children/{student_profile_id}/grades",
        "/api/v1/family-portal/notices",
        "/api/v1/family-portal/notices/{notice_id}/acknowledge",
        "/api/v1/family-admin/access/bootstrap",
        "/api/v1/family-admin/access/grants",
        "/api/v1/family-admin/notices",
    }
    assert expected.issubset(paths)


def test_internal_milestone_routers_keep_required_access_boundaries() -> None:
    for router in (m1_router, m2_router, m3_router, m5_router):
        assert require_staff_access in _dependency_calls(router)

    # M22 delegates intelligence authorization to route-level guards.
    # The M4 parent router must no longer impose coord.console.access.
    assert require_coordination_access not in _dependency_calls(m4_router)


def test_public_students_contract_still_exists() -> None:
    assert "/api/v1/students" in set(app.openapi()["paths"])


def test_m6_events_are_unique_and_namespaced() -> None:
    assert len(M6_EVENT_NAMES) == 6
    assert all("." in event for event in M6_EVENT_NAMES)
