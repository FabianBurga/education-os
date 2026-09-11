from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m11_migration_catalog_and_notice_policy() -> None:
    source = (
        ROOT / "alembic/versions/0013_m11_student_console.py"
    ).read_text(encoding="utf-8")
    for value in (
        "0012_m10",
        "STUDENT",
        "student.console.access",
        "student.profile.view",
        "student.classes.view",
        "student.schedule.view",
        "student.attendance.view",
        "student.grades.view",
        "student.notices.view",
        "student.progress.view",
        "family_notices_select",
        "OWN_STUDENT_NOTICE",
        "GUARDIAN_NOTICE_VISIBLE",
        "STAFF_CURRENT",
    ):
        assert value in source


def test_student_console_routes_cover_read_only_learning_context() -> None:
    source = (
        ROOT / "app/modules/student_console/router.py"
    ).read_text(encoding="utf-8")
    for route in (
        '"/dashboard"',
        '"/me"',
        '"/summary"',
        '"/classes"',
        '"/schedule"',
        '"/attendance"',
        '"/grades"',
        '"/pending"',
        '"/progress"',
        '"/notices"',
    ):
        assert route in source

    assert "@router.post" not in source
    assert "@router.put" not in source
    assert "@router.delete" not in source


def test_student_service_never_accepts_external_student_identifier() -> None:
    source = (
        ROOT / "app/modules/student_console/service.py"
    ).read_text(encoding="utf-8")
    assert "principal.student_profile_id" in source
    assert "student_profile_id: UUID" not in source
    assert "intelligence_signals" not in source


def test_student_dashboard_has_unique_operational_sections() -> None:
    source = (
        ROOT / "app/modules/student_console/student_dashboard.html"
    ).read_text(encoding="utf-8")
    for value in (
        'id="student-token"',
        'id="student-connect"',
        'id="student-profile-name"',
        'id="student-classes-panel"',
        'id="student-schedule-panel"',
        'id="student-attendance-panel"',
        'id="student-grades-panel"',
        'id="student-pending-panel"',
        'id="student-notices-panel"',
        "Student Console actualizado.",
    ):
        assert value in source
