from pathlib import Path

from app.modules.interventions.models import Intervention, InterventionLink

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0021_m21_intervention_core.py"


def test_m21_b1_model_tables():
    assert Intervention.__tablename__ == "interventions"
    assert InterventionLink.__tablename__ == "intervention_links"


def test_m21_b1_revision_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0021_m21_intervention_core"' in src
    assert 'down_revision: str | None = "0020_m21"' in src


def test_m21_b1_intervention_states():
    src = MIGRATION.read_text(encoding="utf-8")
    for value in (
        "OPEN",
        "IN_PROGRESS",
        "MONITORING",
        "RESOLVED",
        "CLOSED",
        "CANCELLED",
    ):
        assert value in src


def test_m21_b1_sensitivity_levels():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "GENERAL" in src
    assert "RESTRICTED" in src
    assert "CONFIDENTIAL" in src


def test_m21_b1_outcome_types():
    src = MIGRATION.read_text(encoding="utf-8")
    for value in (
        "IMPROVED",
        "STABLE",
        "NO_CHANGE",
        "WORSENED",
        "REFERRED",
        "TRANSFERRED",
        "NOT_ASSESSABLE",
    ):
        assert value in src


def test_m21_b1_closed_requires_outcome():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "ck_interventions_closed_requires_outcome" in src
    assert "outcome_recorded_by_user_id IS NOT NULL" in src


def test_m21_b1_permissions_seeded():
    src = MIGRATION.read_text(encoding="utf-8")
    for key in (
        "intervention.read",
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
        "intervention.admin",
    ):
        assert key in src


def test_m21_b1_teacher_is_read_only_by_default():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'READ_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR", "TEACHER")' in src
    assert 'MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")' in src


def test_m21_b1_rls_forced():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'ALTER TABLE "interventions" ENABLE ROW LEVEL SECURITY' in src
    assert 'ALTER TABLE "interventions" FORCE ROW LEVEL SECURITY' in src
    assert 'ALTER TABLE "intervention_links" ENABLE ROW LEVEL SECURITY' in src
    assert 'ALTER TABLE "intervention_links" FORCE ROW LEVEL SECURITY' in src


def test_m21_b1_runtime_has_no_delete_or_truncate():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'GRANT SELECT, INSERT, UPDATE ON "interventions" TO education_app' in src
    assert 'GRANT SELECT, INSERT ON "intervention_links" TO education_app' in src
    assert "GRANT DELETE" not in src
    assert "GRANT TRUNCATE" not in src


def test_m21_b1_teacher_scope_is_active_teaching_scope():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "TEACHER_STUDENT_SCOPE" in src
    assert "teaching_assignments" in src
    assert "student_section_assignments" in src
    assert "e.student_profile_id = interventions.student_profile_id" in src


def test_m21_b1_links_unique_evidence_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "uq_intervention_links_identity" in src
    assert "ORIGIN" in src
    assert "EVIDENCE" in src
    assert "RELATED" in src
    assert "LEGACY_CASE" in src


def test_m21_b1_no_actions_or_followups_yet():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table("intervention_actions"' not in src
    assert 'op.create_table("intervention_followups"' not in src