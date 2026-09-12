from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PERMISSIONS = {
    "finance.console.access",
    "finance.summary.view",
    "finance.concepts.manage",
    "finance.charges.manage",
    "finance.payments.manage",
    "finance.statements.view",
    "finance.reversals.manage",
    "finance.capability.manage",
}


def test_m14_migration_contract() -> None:
    source = (
        ROOT / "alembic" / "versions" / "0016_m14_finance_billing_core.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0016_m14"' in source
    assert 'down_revision: str | None = "0015_m13"' in source
    for permission in EXPECTED_PERMISSIONS:
        assert permission in source

    for table in (
        "billing_concepts",
        "billing_accounts",
        "billing_charges",
        "billing_payments",
        "billing_allocations",
    ):
        assert table in source
        assert f'_enable_staff_rls("{table}")' in source

    assert "'finance.billing'" in source
    assert "'PRIVATE','FISCOMISIONAL'" in source
    assert "'FINANCE_MANAGER'" in source
    assert "INSERT INTO membership_roles" not in source


def test_m14_api_router_is_additive() -> None:
    source = (ROOT / "app" / "api" / "v1" / "router.py").read_text(
        encoding="utf-8"
    )
    assert "m14_router" in source
    assert "router.include_router(m14_router)" in source
    for milestone in (
        "m13_router",
        "m12_router",
        "m11_router",
        "m10_router",
        "m9_router",
    ):
        assert f"router.include_router({milestone})" in source
