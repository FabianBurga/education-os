from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.api.deps import CurrentPrincipal
from app.modules.accountability import metrics_service
from app.modules.accountability.metrics_service import METRIC_IDS, get_metric_definition


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(uuid4(), uuid4(), uuid4())


def test_registry_is_closed_and_contains_frozen_metrics() -> None:
    assert set(METRIC_IDS) == {
        "TIME_TO_DETECTION",
        "TIME_TO_REVIEW",
        "TIME_TO_INTERVENTION",
        "FOLLOW_UP_COMPLIANCE",
        "LOST_CASE_RATE",
        "RECURRENCE_RATE",
        "INTERVENTION_OUTCOME",
        "REVIEW_ACCOUNTABILITY_RATE",
        "DECISION_ACCOUNTABILITY_RATE",
        "NEXT_ACTION_COMPLIANCE",
        "ADMINISTRATIVE_TIME_SAVED",
    }
    with pytest.raises(ValueError):
        get_metric_definition("ARBITRARY_FORMULA")


def test_administrative_time_saved_requires_real_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics_service, "_require", lambda *_args: None)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    result = metrics_service.get_accountability_metric(
        object(),
        _principal(),
        "ADMINISTRATIVE_TIME_SAVED",
        start=start,
        end=start + timedelta(days=1),
    )
    assert result.status == "NOT_COMPUTABLE"
    assert result.reason == "BASELINE_REQUIRED"
    assert result.value is None
    assert result.numerator is None
    assert result.denominator is None


def test_explanation_is_observational_and_versioned() -> None:
    explanation = get_metric_definition("INTERVENTION_OUTCOME")
    assert explanation.metric_version == "m27-6.v1"
    assert "observed" in explanation.business_question.lower()
    assert "caus" not in explanation.definition.lower()
