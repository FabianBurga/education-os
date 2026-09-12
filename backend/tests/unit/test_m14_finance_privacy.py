from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m14_does_not_mix_finance_with_internal_student_risk_reasoning() -> None:
    sources = [
        ROOT / "app" / "modules" / "finance" / "service.py",
        ROOT / "app" / "modules" / "finance" / "finance_dashboard.html",
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


def test_m14_explicitly_excludes_tax_invoice_and_external_payment_processing() -> None:
    dashboard = (
        ROOT / "app" / "modules" / "finance" / "finance_dashboard.html"
    ).read_text(encoding="utf-8")
    service = (
        ROOT / "app" / "modules" / "finance" / "service.py"
    ).read_text(encoding="utf-8").lower()

    assert "No genera factura tributaria SRI" in dashboard
    assert "no procesa tarjetas" in dashboard
    for provider in ("stripe", "paypal", "mercadopago", "datafast"):
        assert provider not in service
