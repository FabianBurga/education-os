from pathlib import Path

from app.modules.interventions.models import (
    InterventionSuggestion,
    InterventionSuggestionEvidence,
)
from app.modules.interventions.schemas import (
    InterventionSuggestionEvidenceRead,
    InterventionSuggestionPage,
    InterventionSuggestionRead,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0023_m21_intervention_suggestions.py"
)


def test_m21_ea_suggestion_models_are_separate_from_intervention():
    assert InterventionSuggestion.__tablename__ == "intervention_suggestions"
    assert (
        InterventionSuggestionEvidence.__tablename__
        == "intervention_suggestion_evidence"
    )
    fields = InterventionSuggestion.model_fields
    assert fields["status"].default == "PENDING"
    assert fields["generation_mode"].default == "RULE_ENGINE"
    assert "accepted_intervention_id" in fields
    assert "reviewed_by_user_id" in fields


def test_m21_ea_suggestion_read_contract_is_explainable():
    fields = InterventionSuggestionRead.model_fields
    assert "rule_key" in fields
    assert "rule_version" in fields
    assert "rationale_summary" in fields
    assert "recommended_intervention_type" in fields
    assert "evidence" in fields
    assert InterventionSuggestionEvidenceRead.model_fields["evidence_id"]
    assert "items" in InterventionSuggestionPage.model_fields


def test_m21_ea_migration_is_additive_and_human_reviewed():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0023_m21_suggestions"' in source
    assert 'down_revision: str | None = "0022_m21_actions_followups"' in source
    assert '"intervention_suggestions"' in source
    assert '"intervention_suggestion_evidence"' in source

    assert "status = 'PENDING'" in source
    assert "status = 'ACCEPTED'" in source
    assert "reviewed_by_user_id IS NOT NULL" in source
    assert "accepted_intervention_id IS NOT NULL" in source
    assert "ck_intervention_suggestions_human_review_boundary" in source


def test_m21_ea_generation_is_deterministic_not_ai():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "generation_mode = 'RULE_ENGINE'" in source
    assert "intervention.suggestion.generate" in source
    assert "intervention.suggestion.review" in source
    assert "AI_COPILOT" not in source
    assert "LLM" not in source


def test_m21_ea_rls_is_forced_and_sensitivity_aware():
    source = MIGRATION.read_text(encoding="utf-8")

    assert (
        'ALTER TABLE "intervention_suggestions" FORCE ROW LEVEL SECURITY'
        in source
    )
    evidence_rls_anchor = source.index(
        'ALTER TABLE "intervention_suggestion_evidence"'
    )
    evidence_rls_block = source[
        evidence_rls_anchor : evidence_rls_anchor + 220
    ]
    assert "FORCE ROW LEVEL SECURITY" in evidence_rls_block
    assert "student_timeline.read_restricted" in source
    assert "student_timeline.read_confidential" in source
    assert "intervention.suggestion.read" in source
    assert "intervention.suggestion.review" in source


def test_m21_ea_manager_roles_receive_suggestion_permissions():
    source = MIGRATION.read_text(encoding="utf-8")

    assert (
        'MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR")'
    ) in source
    role_line = source.split("MANAGER_ROLE_KEYS =", 1)[1].split("\n", 1)[0]
    assert '"TEACHER"' not in role_line


def test_m21_ea_pending_dedupe_is_unique():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "uq_intervention_suggestions_pending_dedupe" in source
    assert "postgresql_where=sa.text(\"status = 'PENDING'\")" in source
