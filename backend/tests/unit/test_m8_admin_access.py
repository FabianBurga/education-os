from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_admin_access_requires_permission_catalog() -> None:
    source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert "def require_admin_access" in source
    assert "admin.console.access" in source
    assert "staff_profiles" in source


def test_m8_router_is_registered() -> None:
    source = (ROOT / "app/api/v1/router.py").read_text(encoding="utf-8")
    assert "m8_router" in source
    assert "router.include_router(m8_router)" in source
