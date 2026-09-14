from uuid import uuid4

from app.modules.intelligence.models import IntelligenceSignal
from app.modules.interventions.suggestion_engine import (
    _RULE_ACADEMIC_MISSING,
    _RULE_ATTENDANCE_ACADEMIC,
    _RULE_REPEATED_LATE,
    _build_candidates,
    _dedupe_key,
)


def _signal(
    signal_type: str,
    *,
    student_id=None,
    period_id=None,
    section_id=None,
    severity="MEDIUM",
    metric=25.0,
    threshold=20.0,
    summary="SOURCE SECRET MUST NOT BE COPIED",
):
    return IntelligenceSignal(
        organization_id=uuid4(),
        institution_id=uuid4(),
        academic_period_id=period_id,
        section_id=section_id,
        student_profile_id=student_id or uuid4(),
        signal_type=signal_type,
        severity=severity,
        metric_value=metric,
        threshold_value=threshold,
        summary=summary,
        status="OPEN",
    )


def test_attendance_academic_correlation_has_precedence():
    student_id = uuid4()
    period_id = uuid4()
    section_id = uuid4()

    signals = [
        _signal(
            "ATTENDANCE_RISK",
            student_id=student_id,
            period_id=period_id,
            section_id=section_id,
            severity="MEDIUM",
            metric=31.0,
            threshold=20.0,
        ),
        _signal(
            "ACADEMIC_RISK",
            student_id=student_id,
            period_id=period_id,
            section_id=section_id,
            severity="MEDIUM",
            metric=62.0,
            threshold=70.0,
        ),
    ]

    candidates = _build_candidates(signals)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.rule_key == _RULE_ATTENDANCE_ACADEMIC
    assert candidate.recommended_intervention_type == "INTEGRATED_SUPPORT"
    assert candidate.sensitivity == "RESTRICTED"
    assert candidate.severity == "HIGH"
    assert set(candidate.evidence_signal_ids) == {signal.id for signal in signals}


def test_academic_missing_work_correlation_suppresses_single_rules():
    student_id = uuid4()
    period_id = uuid4()

    signals = [
        _signal(
            "ACADEMIC_RISK",
            student_id=student_id,
            period_id=period_id,
            severity="MEDIUM",
            metric=66.0,
            threshold=70.0,
        ),
        _signal(
            "MISSING_WORK",
            student_id=student_id,
            period_id=period_id,
            severity="MEDIUM",
            metric=4.0,
            threshold=3.0,
        ),
    ]

    candidates = _build_candidates(signals)

    assert len(candidates) == 1
    assert candidates[0].rule_key == _RULE_ACADEMIC_MISSING
    assert candidates[0].severity == "HIGH"


def test_repeated_late_remains_independent_from_correlation():
    student_id = uuid4()
    period_id = uuid4()

    signals = [
        _signal(
            "ATTENDANCE_RISK",
            student_id=student_id,
            period_id=period_id,
        ),
        _signal(
            "ACADEMIC_RISK",
            student_id=student_id,
            period_id=period_id,
            metric=65.0,
            threshold=70.0,
        ),
        _signal(
            "REPEATED_LATE",
            student_id=student_id,
            period_id=period_id,
            metric=4.0,
            threshold=3.0,
        ),
    ]

    candidates = _build_candidates(signals)
    keys = {candidate.rule_key for candidate in candidates}

    assert keys == {
        _RULE_ATTENDANCE_ACADEMIC,
        _RULE_REPEATED_LATE,
    }


def test_rationale_uses_metrics_not_signal_free_text():
    student_id = uuid4()
    period_id = uuid4()
    source_secret = "PRIVATE SOURCE SUMMARY SHOULD NOT PROPAGATE"

    signals = [
        _signal(
            "ACADEMIC_RISK",
            student_id=student_id,
            period_id=period_id,
            metric=61.5,
            threshold=70.0,
            summary=source_secret,
        )
    ]

    candidate = _build_candidates(signals)[0]

    assert source_secret not in candidate.rationale_summary
    assert "ACADEMIC_RISK" in candidate.rationale_summary
    assert "61.50" in candidate.rationale_summary
    assert "70.00" in candidate.rationale_summary


def test_dedupe_key_is_stable_per_rule_student_period():
    student_id = uuid4()
    period_id = uuid4()

    first = _dedupe_key(
        rule_key=_RULE_ATTENDANCE_ACADEMIC,
        student_profile_id=student_id,
        academic_period_id=period_id,
    )
    second = _dedupe_key(
        rule_key=_RULE_ATTENDANCE_ACADEMIC,
        student_profile_id=student_id,
        academic_period_id=period_id,
    )

    assert first == second
    assert str(student_id) in first
    assert str(period_id) in first


def test_engine_contract_is_deterministic_and_human_bounded():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "suggestion_engine.py"
    ).read_text(encoding="utf-8")

    assert 'generation_mode="RULE_ENGINE"' in source
    assert 'status="PENDING"' in source
    assert 'suggestion.status = "EXPIRED"' in source
    assert "Intervention(" not in source
    assert "accepted_intervention_id" not in source
    assert "INTELLIGENCE_SIGNAL" in source
    assert "student.intervention_suggestion.generated" in source
    assert '"human_authorized": False' in source

    lowered = source.lower()
    assert "openai" not in lowered
    assert "anthropic" not in lowered
    assert "deepseek" not in lowered
    assert "llm" not in lowered
