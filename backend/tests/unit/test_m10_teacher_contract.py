from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_m10_migration_seeds_teacher_role_and_permissions() -> None:
    source = (
        ROOT / "alembic/versions/0012_m10_teacher_console.py"
    ).read_text(encoding="utf-8")
    for value in (
        "0011_m9",
        "teacher.console.access",
        "teacher.classes.view",
        "teacher.attendance.manage",
        "teacher.grades.manage",
        "teacher.tasks.manage",
        "TEACHER",
        "SYSTEM_ADMIN",
    ):
        assert value in source


def test_teacher_dashboard_has_five_operational_blocks() -> None:
    source = (
        ROOT / "app/modules/teacher_console/teacher_dashboard.html"
    ).read_text(encoding="utf-8")
    for label in (
        "Inicio",
        "Mis clases",
        "Asistencia",
        "Calificaciones",
        "Seguimiento",
    ):
        assert label in source


def test_teacher_routes_cover_scoped_learning_loop() -> None:
    source = (
        ROOT / "app/modules/teacher_console/router.py"
    ).read_text(encoding="utf-8")
    for route in (
        '"/summary"',
        '"/classes"',
        '"/classes/{course_offering_id}/roster"',
        '"/classes/{course_offering_id}/sessions"',
        '"/sessions/{class_session_id}/attendance"',
        '"/classes/{course_offering_id}/categories"',
        '"/classes/{course_offering_id}/assessments"',
        '"/assessments/{assessment_id}/grades"',
        '"/alerts"',
        '"/tasks"',
        '"/tasks/{task_id}/acknowledge"',
        '"/tasks/{task_id}/complete"',
    ):
        assert route in source


def test_teacher_service_enforces_teaching_assignment_scope() -> None:
    source = (
        ROOT / "app/modules/teacher_console/service.py"
    ).read_text(encoding="utf-8")
    assert "teaching_assignments" in source
    assert "staff_profile_id" in source
    assert "Course offering is not assigned to the current teacher" in source
    assert "Task is outside the current teacher scope" in source
