"""Static contract tests for the unapplied M26-1 configuration migration."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "0037_m26_mentor_briefing.py"
)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_mentor_migration_has_a_short_linear_revision():
    source = _source()
    assert 'revision: str = "0037_m26_mentor_briefing"' in source
    assert len("0037_m26_mentor_briefing") <= 32
    assert 'down_revision: str | None = "0036_m25_run_explainer"' in source


def test_mentor_seed_is_closed_l0_and_permission_bound():
    source = _source()
    assert '"mentor_institution_briefing"' in source
    assert '"mentor.institution.brief"' in source
    assert '"m22.intelligence_snapshot.inspect"' in source
    assert '"M26_INSTITUTION_BRIEFING"' in source
    for focus in ("OVERVIEW", "PRIORITIES", "FOLLOW_UPS"):
        assert f'"{focus}"' in source
    for permission in ("agents.use", "intelligence.read"):
        assert f'"{permission}"' in source
    assert "'L0', 4, 1," in source


def test_closed_constraints_retain_m25_keys_and_reject_open_registry_design():
    source = _source()
    for key in (
        "integration_run_advisor",
        "student_timeline_advisor",
        "institution_intelligence_advisor",
        "integration_run_explainer",
        "mentor_institution_briefing",
    ):
        assert f"'{key}'" in source
    assert "agent_key IN" in source
    assert "policy_key IN" in source
    assert "request_type IN" in source
    assert "op.create_table" not in source
    assert "GRANT " not in source
    assert "ROW LEVEL SECURITY" not in source


def test_provider_policy_remains_existing_closed_optional_fallback_mode():
    source = _source()
    assert "PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK" in source
    assert '"deterministic_fallback_required":true' in source
    assert '"budget_admission_required":true' in source
    for forbidden in ("PROVIDER_REQUIRED", "ANY_PROVIDER", "ARBITRARY", "UNBOUNDED"):
        assert forbidden not in source


def test_migration_seeds_only_exact_controlled_tenants_without_models_or_credentials():
    source = _source()
    assert "Universidad de Otavalo" in source
    assert "Education OS Local Isolation Secondary" in source
    assert "status = 'ACTIVE'" in source
    assert "agent_model_registry" not in source
    assert "ON CONFLICT" not in source
    for forbidden in ("api_key", "password", "authorization_header", "credential"):
        assert forbidden not in source.lower()


def test_downgrade_removes_exact_seed_only_after_history_guard():
    source = _source()
    assert "Cannot downgrade M26-1 Mentor configuration after execution history exists" in source
    assert "agent_key = :agent_key OR request_type = :request_type" in source
    assert "DELETE FROM agent_policy_versions" in source
    assert "DELETE FROM agent_definitions" in source
    assert "WHERE policy_key = :agent_key AND version = 1" in source
    assert "WHERE agent_key = :agent_key AND version = 1" in source
    assert "substring(" not in source.lower()
