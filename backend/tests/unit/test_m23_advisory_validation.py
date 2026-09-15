from app.modules.copilot import advisory


def test_provider_input_document_uses_opaque_citation_ids():
    evidence = (
        advisory.ProviderEvidence(
            citation_id="E1",
            reference_key="internal:uuid:secret",
            evidence_type="M22_TEST",
            freshness_status="CURRENT",
            source_version="v1",
            content={"priority": "HIGH"},
        ),
    )
    document = advisory._input_document(
        request_text="Summarize.",
        evidence=evidence,
    )

    assert '"citation_id":"E1"' in document
    assert "internal:uuid:secret" not in document


def test_input_budget_estimator_is_conservative():
    estimate = advisory._estimate_input_tokens(
        "x" * 300,
        "y" * 300,
    )
    assert estimate >= 200


def test_output_token_limit_is_bounded():
    assert advisory._max_output_tokens({}) == 1200
    assert advisory._max_output_tokens({"max_output_tokens": 1}) == 256
    assert advisory._max_output_tokens({"max_output_tokens": 9000}) == 4000
