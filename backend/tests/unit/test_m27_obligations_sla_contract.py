from pathlib import Path

from app.modules.accountability.obligation_service import (
    EVIDENCE_TYPES,
    OBLIGATION_TYPES,
    evaluate_obligation_compliance,
)

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0040_m27_obligations_sla.py"
SERVICE = ROOT / "app" / "modules" / "accountability" / "obligation_service.py"


def test_m27_4_bounded_contracts_and_fail_closed_sla_are_present():
    assert OBLIGATION_TYPES == {"INFORMATION_REQUIRED", "REVIEW_REQUIRED", "FOLLOW_UP_REQUIRED"}
    assert EVIDENCE_TYPES == {"M21_FOLLOW_UP", "M21_ACTION", "M27_HUMAN_REVIEW", "M27_INFORMATION"}
    source = SERVICE.read_text(encoding="utf-8")
    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'SLA_POLICY_KEY = "accountability.sla"' in source
    assert '"NOT_EVALUABLE"' in source
    assert "timedelta" in source
    assert "duration_seconds" in source
    assert "24" not in source and "48" not in source and "72" not in source
    assert "accountability.obligation.created" in source
    assert "accountability.obligation.completed" in source
    assert "accountability.obligation.waived" in source
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "intervention_followups" in source
    assert "intervention_actions" in source


def test_m27_4_compliance_boundaries_are_reproducible():
    class Obligation:
        lifecycle = "OPEN"
        due_at = None
        sla_status = "NOT_EVALUABLE"
        completed_at = None

    result = evaluate_obligation_compliance(Obligation())
    assert result.status == "NOT_EVALUABLE"
