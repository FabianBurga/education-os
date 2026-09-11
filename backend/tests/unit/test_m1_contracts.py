from datetime import date

import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.enrollment.router import PeriodCreate
from app.modules.m1_events import M1_EVENT_NAMES


def test_m1_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/students",
        "/api/v1/students/{student_id}",
        "/api/v1/guardians",
        "/api/v1/families",
        "/api/v1/families/{family_id}/members",
        "/api/v1/student-guardian-links",
        "/api/v1/academic-periods",
        "/api/v1/enrollments",
        "/api/v1/enrollments/{enrollment_id}",
        "/api/v1/enrollments/{enrollment_id}/status",
    }
    assert expected.issubset(paths)


def test_period_rejects_reversed_dates() -> None:
    with pytest.raises(ValidationError):
        PeriodCreate(
            code="2026-2027",
            name="2026-2027",
            starts_on=date(2027, 7, 1),
            ends_on=date(2026, 9, 1),
        )


def test_m1_event_names_are_unique_and_namespaced() -> None:
    assert len(M1_EVENT_NAMES) == 8
    assert all("." in name for name in M1_EVENT_NAMES)
