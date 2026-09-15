import pytest
from pydantic import ValidationError

from app.modules.copilot.advisory import AdvisoryAnswerPayload


def test_advisory_answer_payload_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AdvisoryAnswerPayload.model_validate(
            {
                "status": "ANSWER",
                "answer": "Supported answer.",
                "citations": ["E1"],
                "evidence_assessment": "SUFFICIENT",
                "limitations": [],
                "chain_of_thought": "must not persist",
            }
        )


def test_advisory_answer_payload_has_bounded_statuses():
    payload = AdvisoryAnswerPayload.model_validate(
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "answer": "Insufficient evidence.",
            "citations": [],
            "evidence_assessment": "INSUFFICIENT",
            "limitations": ["No eligible evidence."],
        }
    )
    assert payload.status == "INSUFFICIENT_EVIDENCE"
