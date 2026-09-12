from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m15_bootstrap_returns_backend_access_context() -> None:
    source = (
        ROOT / "app" / "modules" / "frontend_ui" / "service.py"
    ).read_text(encoding="utf-8")

    assert "membership_roles" in source
    assert "role_permissions" in source
    assert "institution_capabilities" in source
    assert "staff_profiles" in source
    assert "student_profiles" in source
    assert "guardian_profiles" in source


def test_m15_bootstrap_does_not_make_frontend_an_authorization_source() -> None:
    router = (
        ROOT / "app" / "modules" / "frontend_ui" / "router.py"
    ).read_text(encoding="utf-8")
    navigation = (
        ROOT.parent / "frontend" / "src" / "navigation.ts"
    ).read_text(encoding="utf-8")

    assert "get_current_principal" in router
    assert "permissions" in navigation
    assert "role_permissions" not in navigation
    assert "membership_roles" not in navigation
