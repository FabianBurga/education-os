import pytest
from pydantic import ValidationError

from app.modules.copilot.action_schemas import (
    ActionProposalApproveRequest,
    ActionProposalRejectRequest,
)


def test_action_decision_schemas_forbid_extra_fields():
    with pytest.raises(ValidationError):
        ActionProposalApproveRequest.model_validate(
            {"note": "ok", "execute_anything": True}
        )

    with pytest.raises(ValidationError):
        ActionProposalRejectRequest.model_validate(
            {"reason": "not appropriate", "provider_key": "openai"}
        )


def test_rejection_requires_reason():
    with pytest.raises(ValidationError):
        ActionProposalRejectRequest(reason="")
