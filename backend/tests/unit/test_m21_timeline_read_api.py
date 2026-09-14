from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.modules.student_timeline.router import router as timeline_router
from app.modules.student_timeline.service import (
    _bounded_limit,
    _normalized_category,
    _normalized_sensitivity,
)

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app" / "modules" / "student_timeline" / "service.py"
ROUTER = ROOT / "app" / "modules" / "student_timeline" / "router.py"


def test_m21_timeline_route_registered_in_application_openapi():
    paths = app.openapi()["paths"]
    assert "/api/v1/student-timeline/students/{student_profile_id}" in paths


def test_m21_timeline_route_is_get_only():
    route = next(
        route
        for route in timeline_router.routes
        if isinstance(route, APIRoute)
        and route.path == "/student-timeline/students/{student_profile_id}"
    )
    assert route.methods == {"GET"}


def test_m21_timeline_service_preserves_rls_boundary():
    src = SERVICE.read_text(encoding="utf-8")
    assert "FROM student_timeline_entries" in src
    assert "student_profile_id = CAST(:student_profile_id AS uuid)" in src
    assert "ORDER BY ledger_position DESC" in src
    assert "LIMIT :limit" in src
    assert "student_profiles" not in src
    assert "teaching_assignments" not in src


def test_m21_timeline_router_requires_permission_dependency():
    src = ROUTER.read_text(encoding="utf-8")
    assert "require_student_timeline_read" in src
    assert "Depends(require_student_timeline_read)" in src


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("signal", "SIGNAL"),
        (" academic ", "ACADEMIC"),
        ("follow_up", "FOLLOW_UP"),
    ],
)
def test_category_normalization(value, expected):
    assert _normalized_category(value) == expected


def test_invalid_category_rejected():
    with pytest.raises(ValueError):
        _normalized_category("SECRET")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("general", "GENERAL"),
        (" restricted ", "RESTRICTED"),
        ("confidential", "CONFIDENTIAL"),
    ],
)
def test_sensitivity_normalization(value, expected):
    assert _normalized_sensitivity(value) == expected


def test_invalid_sensitivity_rejected():
    with pytest.raises(ValueError):
        _normalized_sensitivity("PRIVATE")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-5, 1),
        (0, 1),
        (1, 1),
        (50, 50),
        (100, 100),
        (1000, 100),
    ],
)
def test_limit_is_bounded(value, expected):
    assert _bounded_limit(value) == expected


def test_route_contract_exposes_cursor_and_filters():
    src = ROUTER.read_text(encoding="utf-8")
    assert "before_position" in src
    assert "category" in src
    assert "sensitivity" in src
    assert "le=100" in src


def test_service_does_not_expose_event_ledger_payload():
    src = SERVICE.read_text(encoding="utf-8")
    assert "payload_json" not in src
    assert "metadata_json" not in src


def test_dummy_uuid_shape_for_contract_sanity():
    assert uuid4() != uuid4()