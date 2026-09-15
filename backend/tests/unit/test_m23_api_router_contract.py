from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROUTER = ROOT / "app/api/v1/router.py"
COPILOT_ROUTER = ROOT / "app/modules/copilot/router.py"


def test_m23_router_is_mounted_without_global_staff_wrapper():
    source = API_ROUTER.read_text(encoding="utf-8")

    assert "from app.api.v1.m23_router import router as m23_router" in source
    assert "router.include_router(m23_router)" in source
    assert (
        "router.include_router(\n"
        "    m23_router,\n"
        "    dependencies="
    ) not in source


def test_copilot_routes_match_frozen_m23_contract():
    source = COPILOT_ROUTER.read_text(encoding="utf-8")

    assert 'prefix="/copilot"' in source
    assert '"/queries"' in source
    assert '"/runs/{run_id}"' in source
    assert "action-proposals" not in source


def test_copilot_router_does_not_accept_provider_or_model_selection():
    source = COPILOT_ROUTER.read_text(encoding="utf-8")

    assert "provider_key=" not in source
    assert "model_key=" not in source


def test_run_not_visible_is_reported_as_404():
    source = COPILOT_ROUTER.read_text(encoding="utf-8")

    assert "HTTP_404_NOT_FOUND" in source
    assert 'detail="Copilot run not found"' in source
