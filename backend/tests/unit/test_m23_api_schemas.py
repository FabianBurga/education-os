from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.copilot.api_schemas import (
    CopilotQueryRequest,
    CopilotQueryResponse,
)


def test_query_request_rejects_lowercase_freeform_intent():
    with pytest.raises(ValidationError):
        CopilotQueryRequest(
            intent="student support summary",
            request_text="Summarize the authorized evidence.",
        )


def test_query_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        CopilotQueryRequest.model_validate(
            {
                "intent": "STUDENT_SUPPORT_SUMMARY",
                "request_text": "Summarize.",
                "provider_key": "openai",
            }
        )


def test_query_response_contains_only_governed_surface():
    response = CopilotQueryResponse(
        run_id=uuid4(),
        status="REFUSED",
        failure_code="NO_ELIGIBLE_MODEL",
    )
    data = response.model_dump()

    assert "request_text" not in data
    assert "prompt" not in data
    assert "evidence" not in data
    assert "provider_payload" not in data
