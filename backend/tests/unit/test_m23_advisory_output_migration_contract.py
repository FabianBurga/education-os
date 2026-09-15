from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic/versions/0028_m23_advisory_answers.py"


def test_m23_advisory_revision_chain():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0028_m23_advisory_answers"' in source
    assert (
        'down_revision: str | None = "0027_m23_copilot_foundation"'
        in source
    )
    assert len("0028_m23_advisory_answers") <= 32


def test_m23_advisory_output_is_force_rls_and_insert_is_actor_owned():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "copilot_advisory_outputs" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "cr.actor_user_id" in source
    assert "education_os_copilot_run_visible" in source


def test_m23_advisory_output_does_not_store_raw_provider_payload():
    source = MIGRATION.read_text(encoding="utf-8").lower()
    for forbidden in [
        "raw_provider",
        "chain_of_thought",
        "system_prompt",
        "api_key",
        "secret_key",
    ]:
        assert forbidden not in source
