from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_student_console_does_not_expose_internal_risk_labels() -> None:
    service = (
        ROOT / "app/modules/student_console/service.py"
    ).read_text(encoding="utf-8")
    dashboard = (
        ROOT / "app/modules/student_console/student_dashboard.html"
    ).read_text(encoding="utf-8")

    forbidden = (
        "intelligence_signals",
        "ATTENDANCE_RISK",
        "ACADEMIC_RISK",
        "REPEATED_LATE",
    )
    for value in forbidden:
        assert value not in service
        assert value not in dashboard


def test_student_notice_policy_preserves_staff_and_guardian_visibility() -> None:
    migration = (
        ROOT / "alembic/versions/0013_m11_student_console.py"
    ).read_text(encoding="utf-8")
    assert "STAFF_CURRENT" in migration
    assert "GUARDIAN_NOTICE_VISIBLE" in migration
    assert "OWN_STUDENT_NOTICE" in migration
