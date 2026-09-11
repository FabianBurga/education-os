from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_guardian_console_security_has_explicit_permissions() -> None:
    source = (
        ROOT / "app/modules/guardian_console/security.py"
    ).read_text(encoding="utf-8")

    for value in (
        "require_guardian_access",
        "require_guardian_students",
        "require_guardian_schedule",
        "require_guardian_attendance",
        "require_guardian_grades",
        "require_guardian_notices",
        "require_guardian_notice_acknowledgement",
        "require_guardian_progress",
        "guardian.console.access",
        "guardian.students.view",
        "guardian.schedule.view",
        "guardian.attendance.view",
        "guardian.grades.view",
        "guardian.notices.view",
        "guardian.notices.acknowledge",
        "guardian.progress.view",
    ):
        assert value in source


def test_guardian_console_reuses_active_guardian_identity_anchor() -> None:
    source = (
        ROOT / "app/modules/guardian_console/security.py"
    ).read_text(encoding="utf-8")

    assert "get_guardian_principal" in source
    assert "GuardianPrincipal" in source
