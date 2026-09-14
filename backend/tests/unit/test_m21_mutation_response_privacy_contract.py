from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app" / "modules" / "interventions" / "service.py"


def _function_block(source: str, name: str, next_name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.index(f"def {next_name}(", start)
    return source[start:end]


def test_intervention_mutations_sanitize_response():
    source = SERVICE.read_text(encoding="utf-8")
    pairs = (
        ("create_intervention", "assign_intervention"),
        ("assign_intervention", "transition_intervention"),
        ("transition_intervention", "resolve_intervention"),
        ("resolve_intervention", "close_intervention"),
        ("close_intervention", "cancel_intervention"),
        ("cancel_intervention", "_ensure_intervention_operational"),
    )

    for name, next_name in pairs:
        block = _function_block(source, name, next_name)
        assert ") -> InterventionRead:" in block
        assert "return intervention_read_for_principal(" in block
        assert "\n    return entity\n" not in block


def test_action_mutations_sanitize_response():
    source = SERVICE.read_text(encoding="utf-8")
    pairs = (
        ("create_intervention_action", "assign_intervention_action"),
        ("assign_intervention_action", "transition_intervention_action"),
        ("transition_intervention_action", "complete_intervention_action"),
        ("complete_intervention_action", "create_intervention_followup"),
    )

    for name, next_name in pairs:
        block = _function_block(source, name, next_name)
        assert ") -> InterventionActionRead:" in block
        assert "return action_read_for_principal(" in block
        assert "parent_sensitivity=parent.sensitivity" in block
        assert "\n    return action\n" not in block


def test_followup_mutation_sanitizes_response():
    source = SERVICE.read_text(encoding="utf-8")
    block = _function_block(
        source,
        "create_intervention_followup",
        "get_intervention_action",
    )

    assert ") -> InterventionFollowUpRead:" in block
    assert "return followup_read_for_principal(" in block
    assert "\n    return followup\n" not in block


def test_read_sanitizers_remain_centralized():
    source = SERVICE.read_text(encoding="utf-8")
    assert "intervention_read_for_principal" in source
    assert "action_read_for_principal" in source
    assert "followup_read_for_principal" in source
