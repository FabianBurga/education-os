from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic/versions/0027_m23_copilot_foundation.py"
)


def test_m23_foundation_revision_chain_and_permissions():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0027_m23_copilot_foundation"' in source
    assert (
        'down_revision: str | None = "0026_m22_intel_read_boundary"'
        in source
    )
    assert len("0027_m23_copilot_foundation") <= 32
    assert '"copilot.use"' in source
    assert '"copilot.manage"' in source
    assert '"copilot.action.approve"' in source


def test_m23_foundation_creates_governed_tables_and_force_rls():
    source = MIGRATION.read_text(encoding="utf-8")
    for table in [
        "copilot_policy_versions",
        "copilot_prompt_versions",
        "copilot_model_registry",
        "copilot_runs",
        "copilot_evidence_refs",
    ]:
        assert table in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "education_os_copilot_has_permission" in source
    assert "education_os_copilot_is_manager" in source
    assert "education_os_copilot_run_visible" in source


def test_m23_foundation_has_no_provider_secret_columns():
    source = MIGRATION.read_text(encoding="utf-8").lower()
    forbidden = [
        "api_key",
        "secret_key",
        "access_token",
        "password",
        "chain_of_thought",
    ]
    for token in forbidden:
        assert token not in source
