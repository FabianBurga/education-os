from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/architecture/m23-governed-copilot-contract-freeze-v1.md"


def test_m23_contract_exists_and_freezes_core_governance():
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "No raw-database-to-LLM path.",
        "AI may: detect, summarize, recommend, explain.",
        "Human must: verify, decide, approve, act.",
        "`copilot.use`",
        "`copilot.manage`",
        "`copilot.action.approve`",
        "deterministic policy gates",
        "Every substantive Copilot answer must be traceable",
        "The model cannot directly:",
        "High-impact educational",
        "Secrets and hidden chain-of-thought are never persisted.",
        "POST /copilot/queries",
        "POST /copilot/action-proposals/{proposal_id}/approve",
        "wrong tenant",
        "prompt-injection",
        "autonomous high-impact decisions",
    ]
    for token in required:
        assert token.lower() in text.lower()


def test_m23_contract_freezes_human_governed_action_execution():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "M23 may create structured action proposals, never direct actions." in text
    assert "Approval is a new human authorization event." in text
    assert "re-checks permission" in text
    assert "existing authoritative domain service" in text


def test_m23_contract_preserves_m22_and_modular_monolith():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "M22 institutional intelligence" in text
    assert "M23 remains inside the modular monolith for v1." in text
    assert "M23 v1 adds no vector database and no embeddings requirement." in text
    assert "replacement of deterministic M22 intelligence rules with opaque ML" in text
