from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_student_access_has_identity_anchor_and_permissions() -> None:
    source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    for value in (
        "StudentPrincipal",
        "_active_student_profile_id",
        "require_student_profile",
        "require_student_classes",
        "require_student_schedule",
        "require_student_attendance",
        "require_student_grades",
        "require_student_notices",
        "require_student_progress",
        "student.console.access",
        "student.profile.view",
        "student.classes.view",
        "student.schedule.view",
        "student.attendance.view",
        "student.grades.view",
        "student.notices.view",
        "student.progress.view",
    ):
        assert value in source


def test_student_identity_is_person_to_profile_not_arbitrary_student_id() -> None:
    source = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert "student_profiles" in source
    assert "person_id = CAST(:person_id AS uuid)" in source
    assert "Active student profile required" in source
