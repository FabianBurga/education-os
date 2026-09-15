from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0024_m21_projection_boundary.py"
)
PROJECTOR = (
    ROOT
    / "app"
    / "modules"
    / "student_timeline"
    / "projector.py"
)


def test_projection_boundary_migration_contract():
    src = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0024_m21_projection_boundary"' in src
    assert 'down_revision: str | None = "0023_m21_suggestions"' in src
    assert "m21_student_timeline_source_events" in src
    assert "SECURITY DEFINER" in src
    assert "SET search_path = pg_catalog, public" in src
    assert "session_user <> 'education_app'" in src
    assert "admin.console.access" in src
    assert "REVOKE ALL ON FUNCTION" in src
    assert "GRANT EXECUTE ON FUNCTION" in src
    assert "allowed_payload_keys" in src
    assert "ledger_position bigint" in src
    assert "\n            position bigint," not in src
    assert "jsonb_each" in src
    assert "metadata_json" not in src


def test_projection_boundary_whitelists_only_timeline_payload_fields():
    src = MIGRATION.read_text(encoding="utf-8")

    required = {
        "'student_profile_id'",
        "'academic_period_id'",
        "'class_session_id'",
        "'assessment_id'",
        "'signal_type'",
        "'severity'",
        "'sensitivity'",
        "'intervention_id'",
        "'action_id'",
        "'followup_id'",
        "'outcome_type'",
        "'summary'",
    }
    assert required <= {
        token
        for token in required
        if token in src
    }

    forbidden = {
        "'feedback'",
        "'resolution_note'",
        "'outcome_summary'",
        "'cancellation_reason'",
        "'completion_note'",
        "'description'",
    }
    for token in forbidden:
        assert token not in src


def test_projector_consumes_boundary_not_raw_ledger_payload():
    src = PROJECTOR.read_text(encoding="utf-8")

    assert "FROM m21_student_timeline_source_events(" in src
    assert "FROM event_ledger" not in src
    assert "ORDER BY ledger_position" in src
    assert "payload_json" in src
