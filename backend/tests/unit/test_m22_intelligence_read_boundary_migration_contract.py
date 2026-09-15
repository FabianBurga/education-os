import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "alembic" / "versions"
    / "0026_m22_intel_read_boundary.py"
)


def _src() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_revision_contract():
    src = _src()
    assert 'revision: str = "0026_m22_intel_read_boundary"' in src
    assert (
        'down_revision: str | None = "0025_m22_intelligence_foundation"'
        in src
    )


def test_permissions_and_roles():
    src = _src()
    assert '"intelligence.read"' in src
    assert '"intelligence.manage"' in src
    for role in ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR", "TEACHER"):
        assert f'"{role}"' in src


def test_hardens_m4_and_m22_tables():
    src = _src()
    for table in (
        "intelligence_signals",
        "student_intelligence_snapshots",
        "cohort_intelligence_daily",
        "institution_intelligence_daily",
    ):
        assert f'"{table}"' in src
    assert "pg_policies" in src
    assert "_drop_all_policies(table)" in src


def test_teacher_scope_reuses_real_academic_graph():
    src = _src()
    for token in (
        "user_accounts",
        "staff_profiles",
        "teaching_assignments",
        "course_offerings",
        "student_section_assignments",
        "enrollments",
        "target_student_profile_id",
        "target_academic_period_id",
        "ta.starts_on",
        "ta.ends_on",
    ):
        assert token in src


def test_teacher_is_student_scoped():
    src = _src()
    assert "education_os_intelligence_teacher_student_scope(" in src
    assert "STUDENT_SCOPED_TABLES" in src


def test_aggregates_are_manager_only():
    src = _src()
    assert "MANAGER_ONLY_TABLES" in src
    assert "education_os_intelligence_is_manager()" in src


def test_writes_require_manage_and_manager():
    src = _src()
    assert (
        "education_os_intelligence_has_permission('intelligence.manage')"
        in src
    )
    assert "FOR INSERT TO education_app" in src
    assert "FOR UPDATE TO education_app" in src
    assert "FOR DELETE TO education_app" in src


def test_force_rls_preserved():
    src = _src()
    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "FORCE ROW LEVEL SECURITY" in src


def test_downgrade_restores_0025_tenant_policy():
    src = _src()
    assert "def downgrade()" in src
    assert "FOR ALL TO education_app" in src
    assert "WITH CHECK" in src
    assert "DROP FUNCTION IF EXISTS" in src

def test_revision_id_fits_alembic_version_column():
    src = _src()
    match = re.search(r'revision: str = "([^"]+)"', src)
    assert match is not None
    revision_id = match.group(1)
    assert revision_id == "0026_m22_intel_read_boundary"
    assert len(revision_id) <= 32

def test_m4_historical_policy_name_is_preserved_but_hardened():
    src = _src()

    assert '"intelligence_signals_tenant_isolation"' in src
    assert "FOR SELECT TO education_app" in src
    assert (
        "education_os_intelligence_has_permission('intelligence.read')"
        in src
    )
    assert "education_os_intelligence_is_manager()" in src
    assert "education_os_intelligence_teacher_student_scope(" in src

