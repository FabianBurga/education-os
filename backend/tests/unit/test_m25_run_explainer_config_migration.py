"""Static contract tests for the unapplied M25-3C configuration migration."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "0036_m25_run_explainer.py"
)
PROVIDER_MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "0035_m25_governed_provider_execution.py"
)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_explainer_configuration_migration_has_a_short_linear_revision():
    source = _source()
    assert 'revision: str = "0036_m25_run_explainer"' in source
    assert len("0036_m25_run_explainer") <= 32
    assert 'down_revision: str | None = "0035_m25_governed_provider_exec"' in source


def test_explainer_definition_and_closed_typed_request_are_seeded():
    source = _source()
    assert '"integration_run_explainer"' in source
    assert '"integration.run.explain"' in source
    assert '"m24.integration_run.inspect"' in source
    assert '"M24_INTEGRATION_RUN_EXPLAIN"' in source
    for focus in ("SUMMARY", "ERRORS", "OUTCOME"):
        assert f'"{focus}"' in source
    assert "system_prompt" not in source
    assert "prompt_template" not in source


def test_provider_optional_policy_stays_bounded_and_existing_advisors_remain_representable():
    source = _source()
    assert "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK" in source
    assert '"deterministic_fallback_required":true' in source
    assert '"budget_admission_required":true' in source
    assert "'integration_run_advisor','student_timeline_advisor','institution_intelligence_advisor'" in source
    assert "Existing advisor rows are not" in source
    assert "DETERMINISTIC_ONLY policies" in source
    assert "UPDATE agent_" not in source


def test_provider_policy_constraint_remains_closed_without_provider_required_mode():
    source = PROVIDER_MIGRATION.read_text(encoding="utf-8")
    assert "provider_policy IN ('DETERMINISTIC_ONLY','PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK')" in source
    for forbidden in ("PROVIDER_REQUIRED", "ANY_PROVIDER", "ARBITRARY", "UNBOUNDED"):
        assert forbidden not in source


def test_long_frozen_policy_has_a_matching_widened_schema_contract():
    source = _source()
    model_source = (
        Path(__file__).parents[2] / "app" / "modules" / "agents" / "models.py"
    ).read_text(encoding="utf-8")
    frozen = "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK"
    assert len(frozen) > 40
    assert "existing_type=sa.String(length=40)" in source
    assert "type_=sa.String(length=64)" in source
    assert "provider_policy: str = Field(max_length=64)" in model_source


def test_explainer_is_added_only_to_closed_existing_configuration_constraints():
    source = _source()
    assert "agent_key IN" in source
    assert "policy_key IN" in source
    assert "request_type IN" in source
    assert "op.create_table" not in source
    assert "GRANT " not in source
    assert "FORCE ROW LEVEL SECURITY" not in source


def test_migration_seeds_exact_controlled_tenants_without_models_or_credentials():
    source = _source()
    assert "Universidad de Otavalo" in source
    assert "Education OS Local Isolation Secondary" in source
    assert "status = 'ACTIVE'" in source
    assert "agent_model_registry" not in source
    for forbidden_column in ("api_key", "password", "authorization_header"):
        assert f'"{forbidden_column}"' not in source.lower()
    assert "ON CONFLICT" not in source


def test_downgrade_fails_closed_when_execution_history_exists():
    source = _source()
    assert "Cannot downgrade M25-3C explainer seed after execution audit exists" in source
    assert "DELETE FROM agent_policy_versions" in source
    assert "DELETE FROM agent_definitions" in source
    assert "char_length(provider_policy) > 40" in source
    assert "Cannot narrow provider policy column while values exceed 40 characters" in source
    assert "substring(" not in source.lower()
