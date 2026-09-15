from datetime import date
from uuid import uuid4

from app.modules.intelligence.decision_surfaces import (
    _bounded_limit,
    _cohort_read,
    _priority_filter,
)


def test_bounded_limit_is_defensive():
    assert _bounded_limit(-1) == 1
    assert _bounded_limit(50) == 50
    assert _bounded_limit(500) == 100


def test_priority_filter_overall_priority():
    sql, params = _priority_filter(priority="HIGH", dimension=None)
    assert sql == "overall_priority = :priority"
    assert params == {"priority": "HIGH"}


def test_priority_filter_dimension_without_priority_excludes_low():
    sql, params = _priority_filter(
        priority=None,
        dimension="ACADEMIC",
    )
    assert sql == "academic_priority <> 'LOW'"
    assert params == {}


def test_priority_filter_dimension_with_priority_is_exact():
    sql, params = _priority_filter(
        priority="MEDIUM",
        dimension="INTERVENTION",
    )
    assert sql == "intervention_priority = :priority"
    assert params == {"priority": "MEDIUM"}


def test_suppressed_cohort_never_exposes_component_counts():
    row = (
        uuid4(),
        date(2026, 9, 15),
        "SECTION",
        uuid4(),
        1,
        2,
        3,
        4,
        5,
        6,
        True,
        3,
        1,
        1,
        "BUILTIN_DEFAULT",
        1,
        None,
    )

    item = _cohort_read(row)

    assert item.suppressed is True
    assert item.student_count == 3
    assert item.high_priority_count is None
    assert item.medium_priority_count is None
    assert item.attendance_risk_count is None
    assert item.academic_risk_count is None
    assert item.active_intervention_count is None
    assert item.overdue_followup_count is None
