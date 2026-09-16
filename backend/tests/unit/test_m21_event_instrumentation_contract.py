from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app" / "modules"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m21_enrollment_events_are_canonical():
    src = _source("enrollment/service.py") + _source("enrollment/router.py")
    assert 'event_type="student.enrollment.created"' in src
    assert 'event_type="student.enrollment.status_changed"' in src


def test_m21_attendance_events_include_student_identity():
    src = _source("attendance/service.py")
    assert 'event_type="student.attendance.recorded"' in src
    assert 'event_type="student.attendance.updated"' in src
    assert '"student_profile_id": str(enrollment.student_profile_id)' in src


def test_m21_grade_events_include_student_identity():
    src = _source("grades/service.py")
    assert 'event_type="student.grade.recorded"' in src
    assert 'event_type="student.grade.updated"' in src
    assert '"student_profile_id": str(enrollment.student_profile_id)' in src


def test_m21_signal_lifecycle_events():
    src = _source("intelligence/service.py")
    assert 'event_type="student.signal.opened"' in src
    assert 'event_type="student.signal.closed"' in src
    assert 'event_type="student.signal.resolved"' in src
    assert "student.signal.refreshed" not in src


def test_manual_signal_resolve_preserves_actor():
    router = _source("intelligence/router.py")
    coordination = _source("coordination_console/service.py")
    assert "resolve_signal(session, principal, signal_id, payload)" in router
    assert "resolve_signal(session, principal, signal_id, payload)" in coordination
