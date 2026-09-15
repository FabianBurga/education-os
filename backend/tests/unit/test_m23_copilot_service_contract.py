from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/modules/copilot/service.py"
EVIDENCE = ROOT / "app/modules/copilot/evidence.py"


def test_preflight_never_calls_or_imports_provider_sdk():
    source = SERVICE.read_text(encoding="utf-8").lower()
    forbidden = [
        "openai",
        "anthropic",
        "claude",
        "chat.completions",
        "responses.create",
    ]
    for token in forbidden:
        assert token not in source


def test_evidence_assembler_uses_authorized_read_surfaces():
    source = EVIDENCE.read_text(encoding="utf-8")
    assert "require_copilot_use" in source
    assert "require_intelligence_manager_read" in source
    assert "require_student_scope" in source
    assert "student_intelligence_snapshots" in source
