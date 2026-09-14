from pathlib import Path

from app.modules.m21_access import (
    can_access_student,
    has_any_role,
    has_permission,
    is_privileged_m21_staff,
    is_teacher,
    require_student_scope,
    teacher_has_student_scope,
)


def test_m21_da_access_surface_exists():
    assert callable(has_permission)
    assert callable(has_any_role)
    assert callable(is_privileged_m21_staff)
    assert callable(is_teacher)
    assert callable(teacher_has_student_scope)
    assert callable(can_access_student)
    assert callable(require_student_scope)


def test_m21_da_teacher_scope_uses_active_assignment_chain():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "m21_access.py"
    ).read_text(encoding="utf-8")

    required = (
        "user_accounts ua",
        "staff_profiles sp",
        "teaching_assignments ta",
        "course_offerings co",
        "student_section_assignments ssa",
        "enrollments e",
        "sp.status = 'ACTIVE'",
        "co.status = 'ACTIVE'",
        "ssa.status = 'ACTIVE'",
        "ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE",
        "ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE",
    )
    for fragment in required:
        assert fragment in source


def test_m21_da_privileged_roles_are_explicit():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "m21_access.py"
    ).read_text(encoding="utf-8")

    assert '"SYSTEM_ADMIN"' in source
    assert '"RECTOR"' in source
    assert '"ACADEMIC_COORDINATOR"' in source
    assert '"TEACHER"' in source


def test_m21_da_out_of_scope_is_hidden_as_404():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "m21_access.py"
    ).read_text(encoding="utf-8")

    assert "HTTP_404_NOT_FOUND" in source
    assert "Student not found in authorized M21 scope" in source


def test_m21_da_timeline_requires_application_scope_before_read():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "student_timeline"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert "principal: CurrentPrincipal" in source
    assert "require_student_scope(" in source
    assert 'permission_key="student_timeline.read"' in source


def test_m21_da_intervention_reads_require_student_scope():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert source.count("require_student_scope(") >= 5
    assert 'permission_key="intervention.read"' in source


def test_m21_da_router_passes_principal_to_timeline_service():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "student_timeline"
        / "router.py"
    ).read_text(encoding="utf-8")

    assert "principal: TimelinePrincipalDep" in source
    assert "list_student_timeline(\n            session,\n            principal," in source
