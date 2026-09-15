from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/modules/copilot/service.py"


def test_allowed_preflight_flushes_parent_before_evidence_assembly():
    source = SERVICE.read_text(encoding="utf-8")

    denied_branch = source.index("if not selection.decision.allowed:")
    evidence_assembly = source.index(
        "bundle = assemble_governed_evidence(",
        denied_branch,
    )
    parent_flush = source.index(
        "session.flush()",
        denied_branch,
        evidence_assembly,
    )

    assert denied_branch < parent_flush < evidence_assembly


def test_parent_flush_is_not_before_pre_gate_decision():
    source = SERVICE.read_text(encoding="utf-8")

    selection = source.index("selection = evaluate_pre_invocation_policy(")
    denied_branch = source.index("if not selection.decision.allowed:")
    parent_flush = source.index("session.flush()", denied_branch)

    assert selection < denied_branch < parent_flush
