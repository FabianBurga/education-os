from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_guardian_console_does_not_expose_internal_risk_workflows() -> None:
    service = (
        ROOT / "app/modules/guardian_console/service.py"
    ).read_text(encoding="utf-8")
    dashboard = (
        ROOT / "app/modules/guardian_console/guardian_dashboard.html"
    ).read_text(encoding="utf-8")

    forbidden = (
        "intelligence_signals",
        "automation_cases",
        "ATTENDANCE_RISK",
        "ACADEMIC_RISK",
        "REPEATED_LATE",
    )

    for value in forbidden:
        assert value not in service
        assert value not in dashboard


def test_legacy_family_portal_is_not_replaced_by_m12_router() -> None:
    router = (
        ROOT / "app/api/v1/router.py"
    ).read_text(encoding="utf-8")

    assert "m12_router" in router
    assert "m6_router" in router
