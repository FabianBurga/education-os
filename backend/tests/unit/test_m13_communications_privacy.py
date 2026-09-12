from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m13_family_communications_do_not_expose_internal_risk_reasoning() -> None:
    sources = [
        ROOT / "app" / "modules" / "communications" / "service.py",
        ROOT / "app" / "modules" / "communications" / "communications_dashboard.html",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    forbidden = (
        "intelligence_signals",
        "automation_cases",
        "ATTENDANCE_RISK",
        "ACADEMIC_RISK",
        "REPEATED_LATE",
        "risk_score",
    )
    for token in forbidden:
        assert token not in combined


def test_m13_has_no_external_messaging_provider_in_v013() -> None:
    service = (
        ROOT / "app" / "modules" / "communications" / "service.py"
    ).read_text(encoding="utf-8")
    dashboard = (
        ROOT
        / "app"
        / "modules"
        / "communications"
        / "communications_dashboard.html"
    ).read_text(encoding="utf-8")

    assert "twilio" not in service.lower()
    assert "sendgrid" not in service.lower()
    assert "smtp" not in service.lower()
    assert "No envía SMS ni correo externo" in dashboard
