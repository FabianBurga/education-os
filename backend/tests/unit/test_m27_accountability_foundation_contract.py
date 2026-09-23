from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0038_m27_accountability_foundation.py"
PROJECTION = ROOT / "app" / "modules" / "accountability" / "projection.py"


def test_m27_foundation_migration_is_additive_and_rls_bound():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0038_m27_accountability"' in source
    assert 'down_revision: str | None = "0037_m26_mentor_briefing"' in source
    assert 'op.create_table(' in source
    assert '"accountability_cases"' in source
    assert '"accountability_case_sources"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "accountability.view" in source
    assert "accountability.manage" in source
    assert "source_event_id" in source
    assert "source_provenance_sha256" in source
    assert "accountability_cases_update" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "accountability.manage" in source.split("CREATE POLICY accountability_cases_update", 1)[1]
    assert 'def downgrade()' in source
    assert 'op.drop_table("accountability_case_sources")' in source


def test_projection_is_replay_safe_and_does_not_copy_domain_payloads():
    source = PROJECTION.read_text(encoding="utf-8")
    assert "source_fingerprint" in source
    assert "identity_key_sha256" in source
    assert "existing_source" in source
    assert "source_provenance_sha256" in source
    assert "payload_json" not in source
    assert "ON CONFLICT" not in source  # SQLAlchemy uniqueness is handled explicitly before flush
