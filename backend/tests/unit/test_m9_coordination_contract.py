from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m9_migration_seeds_coordination_roles_and_permissions() -> None:
    source = (
        ROOT
        / "alembic/versions/0011_m9_rector_coordination_console.py"
    ).read_text(encoding="utf-8")
    for value in (
        "coord.console.access",
        "coord.analytics.view",
        "coord.signals.manage",
        "coord.cases.manage",
        "RECTOR",
        "ACADEMIC_COORDINATOR",
        "SYSTEM_ADMIN",
    ):
        assert value in source


def test_coordination_dashboard_has_five_operational_blocks() -> None:
    source = (
        ROOT
        / "app/modules/coordination_console/coordination_dashboard.html"
    ).read_text(encoding="utf-8")
    for label in (
        "Resumen",
        "Prioridades",
        "Casos y seguimiento",
        "Secciones",
        "Tendencias",
    ):
        assert label in source


def test_coordination_console_exposes_human_action_loop() -> None:
    source = (
        ROOT
        / "app/modules/coordination_console/router.py"
    ).read_text(encoding="utf-8")
    for route in (
        '"/signals/refresh"',
        '"/signals/{signal_id}/resolve"',
        '"/workflows/run"',
        '"/workflows/tick"',
        '"/tasks/{task_id}/acknowledge"',
        '"/tasks/{task_id}/complete"',
    ):
        assert route in source
