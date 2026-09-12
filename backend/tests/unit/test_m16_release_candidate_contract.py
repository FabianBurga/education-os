from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_m16_release_candidate_is_acceptance_only() -> None:
    release = (
        ROOT
        / "docs"
        / "releases"
        / "m16-full-system-operational-acceptance-v1.0.0-rc6.md"
    ).read_text(encoding="utf-8")

    assert "v1.0.0-rc6" in release
    assert "0016_m14" in release
    assert "no database migration" in release.lower()
    assert "production v1.0.0" in release.lower()


def test_m16_verifier_covers_all_operational_roles() -> None:
    source = (
        ROOT
        / "backend"
        / "tools"
        / "verify_m16_full_system_acceptance.py"
    ).read_text(encoding="utf-8")

    for role in (
        "SYSTEM_ADMIN",
        "RECTOR",
        "ACADEMIC_COORDINATOR",
        "TEACHER",
        "STUDENT",
        "GUARDIAN",
        "FINANCE_MANAGER",
    ):
        assert role in source

    for endpoint in (
        "/api/v1/admin/summary",
        "/api/v1/coordination/summary",
        "/api/v1/teacher/summary",
        "/api/v1/student/me",
        "/api/v1/guardian/me",
        "/api/v1/communications/summary",
        "/api/v1/finance/capability",
        "/api/v1/ui/bootstrap",
        "/api/v1/campuses",
    ):
        assert endpoint in source


def test_m16_verifier_has_positive_negative_and_browser_gates() -> None:
    source = (
        ROOT
        / "backend"
        / "tools"
        / "verify_m16_full_system_acceptance.py"
    ).read_text(encoding="utf-8")

    assert "_verify_api_boundaries" in source
    assert "_verify_rls_negative_tenant" in source
    assert "_verify_browser_role_matrix" in source
    assert "Microsoft Edge multi-role workspace matrix" in source
    assert "Espacio no disponible" in source
    assert "m16_full_system_matrix.json" in source


def test_m16_does_not_redefine_product_authorization() -> None:
    source = (
        ROOT
        / "backend"
        / "tools"
        / "verify_m16_full_system_acceptance.py"
    ).read_text(encoding="utf-8")

    assert "role_permissions" not in source
    assert "permissions" in source
    assert "create_access_token" in source
    assert "institution_id=wrong_institution_id" in source
