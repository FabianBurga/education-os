from app.modules.copilot.models import (
    CopilotEvidenceRef,
    CopilotModelRegistry,
    CopilotPolicyVersion,
    CopilotPromptVersion,
    CopilotRun,
)


def test_m23_copilot_table_names_are_frozen():
    assert CopilotPolicyVersion.__tablename__ == "copilot_policy_versions"
    assert CopilotPromptVersion.__tablename__ == "copilot_prompt_versions"
    assert CopilotModelRegistry.__tablename__ == "copilot_model_registry"
    assert CopilotRun.__tablename__ == "copilot_runs"
    assert CopilotEvidenceRef.__tablename__ == "copilot_evidence_refs"


def test_m23_run_does_not_persist_raw_request_text():
    columns = set(CopilotRun.__table__.columns.keys())
    assert "request_sha256" in columns
    assert "request_text" not in columns
    assert "chain_of_thought" not in columns
