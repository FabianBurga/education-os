from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "app" / "modules"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_enrollment_detail_route_decorator_is_preserved():
    src = _source("enrollment/router.py")
    assert '@router.get("/enrollments/{enrollment_id}", response_model=EnrollmentRead)' in src


def test_rector_dashboard_route_decorator_is_preserved():
    src = _source("intelligence/router.py")
    assert '"/rector/dashboard"' in src
    assert "response_class=HTMLResponse" in src
    assert "include_in_schema=False" in src
