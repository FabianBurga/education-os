from app.modules.intelligence.policy import default_intelligence_policy
from app.modules.intelligence.rules import (
    InterventionFacts,
    evaluate_academic_priority,
    evaluate_attendance_priority,
    evaluate_intervention_priority,
    highest_priority,
)


def test_attendance_priority_uses_semantic_thresholds():
    policy = default_intelligence_policy()

    medium = evaluate_attendance_priority(
        total_records=10,
        absence_percent=25.0,
        late_count=0,
        policy=policy,
    )
    high = evaluate_attendance_priority(
        total_records=10,
        absence_percent=40.0,
        late_count=0,
        policy=policy,
    )

    assert medium.priority == "MEDIUM"
    assert medium.matched_rules == ("attendance_absence_priority_v1",)
    assert high.priority == "HIGH"


def test_attendance_minimum_records_prevents_false_priority():
    policy = default_intelligence_policy()
    result = evaluate_attendance_priority(
        total_records=4,
        absence_percent=100.0,
        late_count=0,
        policy=policy,
    )
    assert result.priority == "LOW"


def test_academic_priority_detects_deterioration_without_mega_score():
    policy = default_intelligence_policy()
    result = evaluate_academic_priority(
        graded_count=4,
        average_percent=75.0,
        missing_count=0,
        previous_average_percent=82.0,
        policy=policy,
    )

    assert result.priority == "MEDIUM"
    assert "academic_deterioration_priority_v1" in result.matched_rules


def test_intervention_overdue_followup_is_high_priority():
    result = evaluate_intervention_priority(
        InterventionFacts(
            active_count=1,
            overdue_followup_count=1,
        )
    )
    assert result.priority == "HIGH"
    assert result.matched_rules == (
        "intervention_followup_overdue_priority_v1",
    )


def test_overall_priority_is_explicit_maximum():
    assert highest_priority("LOW", "MEDIUM", "LOW") == "MEDIUM"
    assert highest_priority("HIGH", "MEDIUM", "LOW") == "HIGH"
