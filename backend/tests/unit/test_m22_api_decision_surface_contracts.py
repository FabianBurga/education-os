from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "app/modules/intelligence/router.py"
SERVICE = ROOT / "app/modules/intelligence/decision_surfaces.py"


LEGACY_PATHS = {
    "/api/v1/intelligence/rector/overview",
    "/api/v1/intelligence/rector/sections",
    "/api/v1/intelligence/rector/trends/attendance",
    "/api/v1/intelligence/rector/trends/academic",
    "/api/v1/intelligence/signals",
    "/api/v1/intelligence/signals/refresh",
    "/api/v1/intelligence/signals/{signal_id}/resolve",
}

NEW_PATHS = {
    "/api/v1/intelligence/overview",
    "/api/v1/intelligence/priorities",
    "/api/v1/intelligence/cohorts",
    "/api/v1/intelligence/trends",
    "/api/v1/intelligence/interventions",
}


def test_m4_and_m22_routes_are_registered():
    paths = set(app.openapi()["paths"])
    assert LEGACY_PATHS.issubset(paths)
    assert NEW_PATHS.issubset(paths)


def test_legacy_router_has_explicit_authorization_guards():
    src = ROUTER.read_text(encoding="utf-8")

    assert src.count("require_intelligence_manager_read(session, principal)") >= 4
    assert "require_intelligence_read(session, principal)" in src
    assert src.count("require_intelligence_manage(session, principal)") >= 2


def test_new_surfaces_do_not_read_raw_event_ledger_or_operational_grades():
    src = SERVICE.read_text(encoding="utf-8")

    forbidden = (
        "event_ledger",
        "payload_json",
        "attendance_records",
        "grade_entries",
        "assessments",
        "class_sessions",
    )
    for token in forbidden:
        assert token not in src


def test_new_surface_lists_are_bounded():
    src = SERVICE.read_text(encoding="utf-8")

    assert "def _bounded_limit" in src
    assert "min(int(limit), 100)" in src
    assert src.count("LIMIT :limit") >= 2


def test_trends_use_latest_slice_per_day_without_prediction():
    src = SERVICE.read_text(encoding="utf-8")

    assert "DISTINCT ON (snapshot_date)" in src
    assert "ORDER BY snapshot_date, created_at DESC, id DESC" in src
    for token in ("predict", "forecast", "smooth", "interpolate"):
        assert token not in src.lower()
