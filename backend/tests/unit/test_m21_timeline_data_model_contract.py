from pathlib import Path

from app.modules.student_timeline.models import StudentTimelineEntry

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0020_m21_student_timeline.py"
ACCESS = ROOT / "app" / "api" / "access.py"


def test_m21_timeline_model_contract():
    table = StudentTimelineEntry.__table__
    assert table.name == "student_timeline_entries"
    required = {
        "id", "organization_id", "institution_id", "student_profile_id",
        "ledger_event_id", "ledger_position", "event_type", "event_version",
        "category", "importance", "sensitivity", "title", "summary",
        "source_aggregate_type", "source_aggregate_id", "actor_user_id",
        "correlation_id", "causation_id", "context_json", "occurred_at",
        "recorded_at", "projected_at",
    }
    assert required <= set(table.columns.keys())


def test_m21_migration_revision_and_idempotency_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0020_m21"' in src
    assert 'down_revision: str | None = "0019_m20"' in src
    assert "uq_student_timeline_inst_ledger_event" in src
    assert "ledger_position > 0" in src
    assert "event_version >= 1" in src


def test_m21_timeline_sensitivity_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "GENERAL','RESTRICTED','CONFIDENTIAL" in src
    assert "student_timeline.read" in src
    assert "student_timeline.read_restricted" in src
    assert "student_timeline.read_confidential" in src
    assert "TEACHER_STUDENT_SCOPE" in src


def test_m21_timeline_rls_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "FORCE ROW LEVEL SECURITY" in src
    assert "student_timeline_entries_select" in src
    assert "student_timeline_entries_insert" in src
    assert "admin.console.access" in src


def test_m21_timeline_access_dependencies():
    src = ACCESS.read_text(encoding="utf-8")
    assert "def require_student_timeline_read(" in src
    assert "def require_student_timeline_restricted(" in src
    assert "def require_student_timeline_confidential(" in src
