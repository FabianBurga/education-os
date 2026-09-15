from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTOR = ROOT / "app" / "modules" / "intelligence" / "projector.py"
SERVICE = ROOT / "app" / "modules" / "intelligence" / "service.py"


def test_m22_projector_uses_real_operational_sources():
    src = PROJECTOR.read_text(encoding="utf-8")

    required = {
        "attendance_records",
        "attendance_codes",
        "counts_as_absent",
        "counts_as_late",
        "class_sessions",
        "grading_periods",
        "grade_entries",
        "assessments",
        "intelligence_signals",
        "interventions",
        "intervention_actions",
        "intervention_followups",
    }
    for token in required:
        assert token in src

    assert "event_ledger" not in src
    assert "payload_json" not in src


def test_m22_projector_materializes_exact_0025_read_models():
    src = PROJECTOR.read_text(encoding="utf-8")

    for table in (
        "student_intelligence_snapshots",
        "cohort_intelligence_daily",
        "institution_intelligence_daily",
    ):
        assert table in src

    assert "PROJECTION_VERSION = 1" in src
    assert "RULE_SET_VERSION" in src
    assert "minimum_cohort_size" in src
    assert "suppressed" in src
    assert "window_start" in src
    assert "window_end" in src


def test_m22_projector_does_not_own_transaction_boundary():
    src = PROJECTOR.read_text(encoding="utf-8")

    assert "session.commit()" not in src
    assert "caller owns transaction boundaries" in src


def test_m4_signal_refresh_consumes_m22_policy_resolver():
    src = SERVICE.read_text(encoding="utf-8")

    assert "resolve_intelligence_policy" in src
    assert "policy.attendance.minimum_records" in src
    assert "policy.attendance.absence_threshold_percent" in src
    assert "policy.attendance.late_count_threshold" in src
    assert "policy.academic.minimum_graded_records" in src
    assert "policy.academic.average_threshold_percent" in src
    assert "policy.academic.missing_work_threshold" in src
