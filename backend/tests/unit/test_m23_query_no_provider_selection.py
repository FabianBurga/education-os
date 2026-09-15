from app.modules.copilot.api_schemas import CopilotQueryRequest


def test_api_request_cannot_choose_provider_model_or_prompt():
    fields = set(CopilotQueryRequest.model_fields)

    assert fields == {
        "intent",
        "request_text",
        "target_student_profile_id",
    }
