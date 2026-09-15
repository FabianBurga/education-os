from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_coordination_access_requires_explicit_permission() -> None:
    source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert "def require_coordination_access" in source
    for permission in (
        "coord.console.access",
        "coord.analytics.view",
        "coord.signals.manage",
        "coord.cases.manage",
    ):
        assert permission in source
    assert "staff_profiles" in source
    assert "memberships" in source


def test_m4_intelligence_is_upgraded_to_coordination_boundary() -> None:
    source = (ROOT / "app/api/v1/m4_router.py").read_text(encoding="utf-8")
    assert "require_coordination_access" not in source
    assert "router = APIRouter()" in source
    assert "router.include_router(intelligence_router)" in source

    intelligence_source = (
        ROOT / "app/modules/intelligence/router.py"
    ).read_text(encoding="utf-8")
    assert "require_intelligence_read" in intelligence_source
    assert "require_intelligence_manager_read" in intelligence_source
    assert "require_intelligence_manage" in intelligence_source
    assert "require_staff_access" not in source


def test_m9_router_is_registered() -> None:
    source = (ROOT / "app/api/v1/router.py").read_text(encoding="utf-8")
    assert "m9_router" in source
    assert "router.include_router(m9_router)" in source
