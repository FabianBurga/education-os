from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m8_migration_adds_narrow_account_policies() -> None:
    source = (
        ROOT
        / "alembic/versions/0010_m8_administrator_console.py"
    ).read_text(encoding="utf-8")
    assert (
        "GRANT INSERT, UPDATE ON TABLE user_accounts TO education_app"
        in source
    )
    assert "user_accounts_admin_insert_policy" in source
    assert "user_accounts_admin_update_policy" in source
    assert "admin.console.access" in source
    assert "GRANT DELETE" not in source


def test_admin_dashboard_has_five_operational_blocks() -> None:
    source = (
        ROOT
        / "app/modules/admin_console/admin_dashboard.html"
    ).read_text(encoding="utf-8")
    for label in (
        "Institución",
        "Personas y accesos",
        "Estructura académica",
        "Matrícula y familias",
        "Puesta en marcha",
    ):
        assert label in source
