import json

import pytest

from app.modules.copilot.providers import (
    OpenAIResponsesProvider,
    ProviderGateway,
    ProviderGatewayError,
    ProviderRequest,
)


def _request():
    return ProviderRequest(
        model_key="gpt-test",
        instructions="Governed instructions.",
        input_text='{"evidence":[]}',
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        max_output_tokens=700,
    )


def test_openai_payload_is_non_storing_structured_and_tool_free():
    provider = OpenAIResponsesProvider()
    payload = provider.build_payload(_request())

    assert payload["store"] is False
    assert payload["truncation"] == "disabled"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert "tools" not in payload
    assert "previous_response_id" not in payload
    assert "metadata" not in payload


def test_openai_adapter_reads_key_only_from_environment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIResponsesProvider()

    with pytest.raises(ProviderGatewayError) as error:
        provider.invoke(_request())

    assert error.value.code == "PROVIDER_CREDENTIAL_MISSING"


def test_gateway_fails_closed_for_unknown_provider():
    gateway = ProviderGateway(providers={})

    with pytest.raises(ProviderGatewayError) as error:
        gateway.invoke("unregistered-provider", _request())

    assert error.value.code == "PROVIDER_NOT_SUPPORTED"


def test_openai_output_parser_accepts_structured_output_text():
    provider = OpenAIResponsesProvider()
    text = provider._extract_output_text(
        {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "status": "ANSWER",
                                    "answer": "A",
                                    "citations": ["E1"],
                                    "evidence_assessment": "SUFFICIENT",
                                    "limitations": [],
                                }
                            ),
                        }
                    ],
                }
            ]
        }
    )
    assert '"status": "ANSWER"' in text
