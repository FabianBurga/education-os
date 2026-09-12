from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m14_capability_is_required_for_operational_finance_permissions() -> None:
    security = (
        ROOT / "app" / "modules" / "finance" / "security.py"
    ).read_text(encoding="utf-8")

    assert 'CAPABILITY_KEY = "finance.billing"' in security
    assert "finance_capability_enabled" in security
    assert "require_capability=False" in security
    assert "Finance / Billing capability is disabled" in security


def test_m14_capability_management_is_separate_permission() -> None:
    migration = (
        ROOT / "alembic" / "versions" / "0016_m14_finance_billing_core.py"
    ).read_text(encoding="utf-8")
    security = (
        ROOT / "app" / "modules" / "finance" / "security.py"
    ).read_text(encoding="utf-8")

    assert '"finance.capability.manage"' in migration
    assert '"finance.capability.manage"' in security
    assert "RECTOR_PERMISSIONS" in migration
    assert "FINANCE_MANAGER_PERMISSIONS" in migration
