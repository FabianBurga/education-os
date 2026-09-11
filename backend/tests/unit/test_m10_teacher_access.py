from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_teacher_access_has_scoped_permissions() -> None:
    source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    for value in (
        "TeacherPrincipal",
        "require_teacher_classes",
        "require_teacher_attendance",
        "require_teacher_grades",
        "require_teacher_tasks",
        "teacher.console.access",
        "teacher.classes.view",
        "teacher.attendance.manage",
        "teacher.grades.manage",
        "teacher.tasks.manage",
    ):
        assert value in source


def test_teacher_only_actor_is_blocked_from_broad_legacy_staff_surfaces() -> None:
    access_source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert "def require_privileged_staff_access" in access_source
    assert "Teacher-only actors must use scoped Teacher Console APIs" in access_source

    for path in (
        "app/api/v1/m1_router.py",
        "app/api/v1/m2_router.py",
        "app/api/v1/m3_router.py",
        "app/api/v1/m5_router.py",
        "app/modules/family_portal/admin_router.py",
        "app/modules/operations/router.py",
    ):
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "require_privileged_staff_access" in source
