from pathlib import Path

from app.modules.accountability.queue_service import QUEUE_NEXT_STEPS, QUEUE_REASONS


def test_queue_contract_has_bounded_reasons_and_next_steps() -> None:
    assert QUEUE_REASONS == {
        "UNASSIGNED", "REVIEW_REQUIRED", "DECISION_REQUIRED",
        "INFORMATION_REQUIRED", "FOLLOW_UP_REQUIRED", "OBLIGATION_DUE",
        "OBLIGATION_OVERDUE",
    }
    assert QUEUE_NEXT_STEPS == {
        "ASSIGN_OWNER", "HUMAN_REVIEW", "RECORD_DECISION",
        "PROVIDE_INFORMATION", "COMPLETE_FOLLOW_UP", "WAIT_FOR_DUE_DATE",
        "NO_IMMEDIATE_ACTION",
    }


def test_review_reason_and_obligation_next_step_are_distinct_vocabularies() -> None:
    assert "REVIEW_REQUIRED" in QUEUE_REASONS
    assert "HUMAN_REVIEW_REQUIRED" not in QUEUE_REASONS
    assert "HUMAN_REVIEW_REQUIRED" not in QUEUE_NEXT_STEPS


def test_queue_is_read_only_and_has_no_opaque_score() -> None:
    source = Path("app/modules/accountability/queue_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO" not in source
    assert "UPDATE accountability" not in source
    assert "attention_score" not in source
    assert "risk_score" not in source
    assert "queue.viewed" not in source
