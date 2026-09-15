from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/modules/copilot/api_service.py"


def test_run_read_is_tenant_bounded_and_rls_backed():
    source = SERVICE.read_text(encoding="utf-8")

    assert "FROM copilot_runs cr" in source
    assert "cr.organization_id = CAST(:organization_id AS uuid)" in source
    assert "cr.institution_id = CAST(:institution_id AS uuid)" in source
    assert "copilot_evidence_refs" not in source


def test_run_read_exposes_only_validated_advisory_output():
    source = SERVICE.read_text(encoding="utf-8")

    assert "LEFT JOIN copilot_advisory_outputs cao" in source
    assert "cao.answer_text" in source
    assert "cao.citations_json" in source
    assert "content_json" not in source
    assert "template_text" not in source


def test_run_read_does_not_return_provider_raw_payload_or_secrets():
    source = SERVICE.read_text(encoding="utf-8").lower()

    for forbidden in [
        "raw_provider",
        "api_key",
        "secret_key",
        "chain_of_thought",
        "system_prompt",
    ]:
        assert forbidden not in source
