from __future__ import annotations

from dataclasses import dataclass

from app.modules.intelligence.policy import ResolvedIntelligencePolicy

RULE_SET_VERSION = 1

PRIORITY_LOW = "LOW"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_HIGH = "HIGH"

ATTENDANCE_HIGH_ABSENCE_PERCENT = 35.0
ACADEMIC_HIGH_AVERAGE_PERCENT = 50.0


@dataclass(frozen=True, slots=True)
class RuleResult:
    priority: str
    matched_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterventionFacts:
    active_count: int = 0
    without_action_count: int = 0
    overdue_followup_count: int = 0
    unresolved_outcome_count: int = 0
    worsened_outcome_count: int = 0
    positive_outcome_count: int = 0


def highest_priority(*priorities: str) -> str:
    if PRIORITY_HIGH in priorities:
        return PRIORITY_HIGH
    if PRIORITY_MEDIUM in priorities:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def evaluate_attendance_priority(
    *,
    total_records: int,
    absence_percent: float | None,
    late_count: int,
    policy: ResolvedIntelligencePolicy,
) -> RuleResult:
    priority = PRIORITY_LOW
    matched: list[str] = []

    if (
        total_records >= policy.attendance.minimum_records
        and absence_percent is not None
        and absence_percent >= policy.attendance.absence_threshold_percent
    ):
        matched.append("attendance_absence_priority_v1")
        priority = (
            PRIORITY_HIGH
            if absence_percent >= ATTENDANCE_HIGH_ABSENCE_PERCENT
            else PRIORITY_MEDIUM
        )

    if late_count >= policy.attendance.late_count_threshold:
        matched.append("attendance_late_priority_v1")
        late_priority = (
            PRIORITY_HIGH
            if late_count >= policy.attendance.late_count_threshold * 2
            else PRIORITY_MEDIUM
        )
        priority = highest_priority(priority, late_priority)

    return RuleResult(priority=priority, matched_rules=tuple(matched))


def evaluate_academic_priority(
    *,
    graded_count: int,
    average_percent: float | None,
    missing_count: int,
    previous_average_percent: float | None,
    policy: ResolvedIntelligencePolicy,
) -> RuleResult:
    priority = PRIORITY_LOW
    matched: list[str] = []

    if (
        graded_count >= policy.academic.minimum_graded_records
        and average_percent is not None
        and average_percent < policy.academic.average_threshold_percent
    ):
        matched.append("academic_average_priority_v1")
        average_priority = (
            PRIORITY_HIGH
            if average_percent < ACADEMIC_HIGH_AVERAGE_PERCENT
            else PRIORITY_MEDIUM
        )
        priority = highest_priority(priority, average_priority)

    if missing_count >= policy.academic.missing_work_threshold:
        matched.append("academic_missing_work_priority_v1")
        missing_priority = (
            PRIORITY_HIGH
            if missing_count >= policy.academic.missing_work_threshold * 2
            else PRIORITY_MEDIUM
        )
        priority = highest_priority(priority, missing_priority)

    if (
        average_percent is not None
        and previous_average_percent is not None
        and average_percent < previous_average_percent
    ):
        matched.append("academic_deterioration_priority_v1")
        deterioration_priority = (
            PRIORITY_HIGH
            if average_percent < ACADEMIC_HIGH_AVERAGE_PERCENT
            else PRIORITY_MEDIUM
        )
        priority = highest_priority(priority, deterioration_priority)

    return RuleResult(priority=priority, matched_rules=tuple(matched))


def evaluate_intervention_priority(
    facts: InterventionFacts,
) -> RuleResult:
    priority = PRIORITY_LOW
    matched: list[str] = []

    if facts.without_action_count > 0:
        matched.append("intervention_no_action_priority_v1")
        priority = PRIORITY_MEDIUM

    if facts.overdue_followup_count > 0:
        matched.append("intervention_followup_overdue_priority_v1")
        priority = PRIORITY_HIGH

    if facts.unresolved_outcome_count > 0:
        matched.append("intervention_unresolved_outcome_priority_v1")
        outcome_priority = (
            PRIORITY_HIGH
            if facts.worsened_outcome_count > 0
            else PRIORITY_MEDIUM
        )
        priority = highest_priority(priority, outcome_priority)

    return RuleResult(priority=priority, matched_rules=tuple(matched))
