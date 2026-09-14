from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
ACCESS = ROOT / "app" / "api" / "access.py"
SERVICE = ROOT / "app" / "modules" / "interventions" / "service.py"
ROUTER = ROOT / "app" / "modules" / "interventions" / "router.py"
M21_ROUTER = ROOT / "app" / "api" / "v1" / "m21_router.py"


def test_m21_b4_routes_are_registered():
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/interventions",
        "/api/v1/interventions/{intervention_id}",
        "/api/v1/interventions/students/{student_profile_id}",
        "/api/v1/interventions/{intervention_id}/assign",
        "/api/v1/interventions/{intervention_id}/transition",
        "/api/v1/interventions/{intervention_id}/resolve",
        "/api/v1/interventions/{intervention_id}/close",
        "/api/v1/interventions/{intervention_id}/cancel",
    }
    assert expected <= set(paths)


def test_m21_b4_access_dependencies_cover_all_management_permissions():
    src = ACCESS.read_text(encoding="utf-8")
    for permission in (
        "intervention.read",
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
    ):
        assert f'"{permission}"' in src


def test_m21_b4_read_service_relies_on_rls_and_does_not_probe_student():
    src = SERVICE.read_text(encoding="utf-8")
    body = src.split("def list_student_interventions", maxsplit=1)[1]
    body = body.split("\ndef ", maxsplit=1)[0]
    assert "_assert_student_in_tenant" not in body
    assert "select(Intervention)" in body
    assert "intervention.read" in body


def test_m21_b4_router_delegates_mutations_to_service():
    src = ROUTER.read_text(encoding="utf-8")
    assert "session.commit()" not in src
    assert "enqueue_canonical_event" not in src
    for name in (
        "create_intervention",
        "assign_intervention",
        "transition_intervention",
        "resolve_intervention",
        "close_intervention",
        "cancel_intervention",
    ):
        assert name in src


def test_m21_b4_m21_router_composes_both_surfaces():
    src = M21_ROUTER.read_text(encoding="utf-8")
    assert "include_router(student_timeline_router)" in src
    assert "include_router(intervention_router)" in src


def test_m21_b4_filters_are_bounded():
    src = ROUTER.read_text(encoding="utf-8")
    assert "ge=1, le=100" in src
    assert "GENERAL|RESTRICTED|CONFIDENTIAL" in src


def test_m21_b4_response_schema_is_orm_compatible():
    from app.modules.interventions.schemas import InterventionRead

    assert InterventionRead.model_config.get("from_attributes") is True