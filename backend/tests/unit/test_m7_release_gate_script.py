from pathlib import Path


def test_m7_release_gate_script_exists() -> None:
    script = Path(__file__).resolve().parents[2] / "tools" / "verify_m7_release_gate.py"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "check_runtime_role" in text
    assert "check_critical_rls" in text
    assert "check_api_contracts" in text
    assert "check_operations_staff_boundary" in text
