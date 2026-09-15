import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/modules/interventions/service.py"


def test_create_intervention_supports_transaction_control_without_breaking_default():
    source = SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "create_intervention":
            target = node
            break

    assert target is not None
    kwonly = [arg.arg for arg in target.args.kwonlyargs]
    assert "commit" in kwonly

    segment = ast.get_source_segment(source, target) or ""
    assert "commit: bool = True" in segment
    assert "if commit:" in segment
    assert "session.commit()" in segment
    assert "session.flush()" in segment
