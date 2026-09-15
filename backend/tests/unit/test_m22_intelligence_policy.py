import pytest

from app.modules.intelligence.policy import (
    POLICY_SOURCE_CONTROL_PLANE,
    IntelligencePolicyError,
    default_intelligence_policy,
    policy_from_document,
)


def test_default_m22_policy_preserves_m4_thresholds():
    policy = default_intelligence_policy()

    assert policy.attendance.absence_threshold_percent == 20.0
    assert policy.attendance.minimum_records == 5
    assert policy.attendance.late_count_threshold == 3
    assert policy.academic.average_threshold_percent == 70.0
    assert policy.academic.minimum_graded_records == 2
    assert policy.academic.missing_work_threshold == 3
    assert policy.intervention.followup_overdue_calendar_days == 7
    assert policy.privacy.minimum_cohort_size == 5
    assert policy.persistence.minimum_consecutive_snapshots == 2
    assert policy.policy_source == "BUILTIN_DEFAULT"
    assert policy.control_revision is None


def test_control_plane_policy_supports_partial_overrides():
    policy = policy_from_document(
        {
            "attendance": {"absence_threshold_percent": 18},
            "privacy": {"minimum_cohort_size": 7},
        },
        source=POLICY_SOURCE_CONTROL_PLANE,
        version=4,
        control_revision=9,
    )

    assert policy.attendance.absence_threshold_percent == 18.0
    assert policy.attendance.minimum_records == 5
    assert policy.academic.average_threshold_percent == 70.0
    assert policy.privacy.minimum_cohort_size == 7
    assert policy.policy_version == 4
    assert policy.control_revision == 9


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            {"attendance": {"absence_threshold_percent": 101}},
            "absence_threshold_percent",
        ),
        (
            {"academic": {"minimum_graded_records": 0}},
            "minimum_graded_records",
        ),
        (
            {"privacy": {"minimum_cohort_size": 1}},
            "minimum_cohort_size",
        ),
    ],
)
def test_invalid_policy_values_are_rejected(document, message):
    with pytest.raises(IntelligencePolicyError, match=message):
        policy_from_document(
            document,
            source=POLICY_SOURCE_CONTROL_PLANE,
            version=1,
            control_revision=1,
        )


def test_control_plane_policy_requires_managed_revision():
    with pytest.raises(
        IntelligencePolicyError,
        match="positive control revision",
    ):
        policy_from_document(
            {},
            source=POLICY_SOURCE_CONTROL_PLANE,
            version=1,
            control_revision=None,
        )
