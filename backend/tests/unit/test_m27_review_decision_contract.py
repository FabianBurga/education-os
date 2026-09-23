from pathlib import Path

from app.modules.accountability.ledger_service import DECISION_TYPES, REVIEW_DISPOSITIONS

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0039_m27_review_decision.py"
SERVICE = ROOT / "app" / "modules" / "accountability" / "ledger_service.py"


def test_m27_3_bounded_vocabularies_are_frozen():
    assert REVIEW_DISPOSITIONS == {
        "CONFIRMED", "NEEDS_INFORMATION", "CONTINUE_MONITORING",
        "READY_FOR_DECISION", "NO_CURRENT_CONCERN",
    }
    assert DECISION_TYPES == {
        "NO_ACTION_REQUIRED", "MONITOR", "REQUEST_INFORMATION",
        "CREATE_INTERVENTION", "CONTINUE_INTERVENTION", "ESCALATE", "CLOSE_CASE",
    }


def test_m27_3_migration_is_append_only_and_rls_bound():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0039_m27_review_decision"' in source
    assert 'down_revision: str | None = "0038_m27_accountability"' in source
    for table in ("accountability_reviews", "accountability_decisions", "accountability_ownership_events"):
        assert f'"{table}"' in source
    assert 'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in source
    assert 'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY' in source
    assert 'GRANT SELECT, INSERT ON "{table}" TO education_app' in source
    assert "accountability.review" in source
    assert "accountability.decide" in source
    assert "accountability.ownership.manage" in source
    assert "op.drop_table" in source  # development rollback only


def test_m27_3_recording_does_not_import_or_execute_m21_mutations():
    source = SERVICE.read_text(encoding="utf-8")
    assert "modules.interventions" not in source
    assert "create_intervention" not in source
    assert "intervention_actions" not in source
    assert "intervention_followups" not in source
    assert "enqueue_canonical_event" in source
    assert "record_audit" in source
