from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m12_migration_catalog_is_explicit_and_non_assigning() -> None:
    source = (
        ROOT / "alembic/versions/0014_m12_guardian_console.py"
    ).read_text(encoding="utf-8")

    for value in (
        'revision: str = "0014_m12"',
        'down_revision: str | None = "0013_m11"',
        "'GUARDIAN'",
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

    assert "INSERT INTO membership_roles" not in source
    assert "guardian_student_portal_access" not in source


def test_m12_routes_cover_family_learning_context() -> None:
    source = (
        ROOT / "app/modules/guardian_console/router.py"
    ).read_text(encoding="utf-8")

    for route in (
        '"/dashboard"',
        '"/me"',
        '"/students"',
        '"/students/{student_profile_id}/summary"',
        '"/students/{student_profile_id}/classes"',
        '"/students/{student_profile_id}/schedule"',
        '"/students/{student_profile_id}/attendance"',
        '"/students/{student_profile_id}/grades"',
        '"/students/{student_profile_id}/pending"',
        '"/students/{student_profile_id}/progress"',
        '"/notices"',
        '"/notices/{notice_id}/acknowledge"',
    ):
        assert route in source

    assert "@router.put" not in source
    assert "@router.patch" not in source
    assert "@router.delete" not in source


def test_guardian_service_checks_active_portal_grant_for_student_routes() -> None:
    source = (
        ROOT / "app/modules/guardian_console/service.py"
    ).read_text(encoding="utf-8")

    assert "def _require_student_scope" in source
    assert "guardian_student_portal_access" in source
    assert "pa.status = 'ACTIVE'" in source
    assert "guardian.guardian_profile_id" in source
    assert "Student not available in Guardian Console" in source


def test_guardian_dashboard_has_operational_acceptance_targets() -> None:
    source = (
        ROOT / "app/modules/guardian_console/guardian_dashboard.html"
    ).read_text(encoding="utf-8")

    for value in (
        'id="guardian-token"',
        'id="guardian-connect"',
        'id="guardian-students-list"',
        'id="guardian-selected-title"',
        'id="guardian-tab-notices"',
        'id="guardian-notices-body"',
        "Guardian Console actualizado.",
        "Aviso confirmado.",
    ):
        assert value in source
