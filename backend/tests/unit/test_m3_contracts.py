from datetime import time

import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.attendance.schemas import ClassSessionCreate
from app.modules.grades.schemas import GradingScaleCreate
from app.modules.m3_events import M3_EVENT_NAMES


def test_m3_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/attendance/codes",
        "/api/v1/attendance/sessions",
        "/api/v1/attendance/sessions/{class_session_id}/records",
        "/api/v1/grades/periods",
        "/api/v1/grades/scales",
        "/api/v1/grades/scales/{scale_id}/bands",
        "/api/v1/grades/categories",
        "/api/v1/grades/assessments",
        "/api/v1/grades/assessments/{assessment_id}/entries",
    }
    assert expected.issubset(paths)


def test_class_session_rejects_invalid_time_range() -> None:
    with pytest.raises(ValidationError):
        ClassSessionCreate(
            course_offering_id="11111111-1111-1111-1111-111111111111",
            session_date="2026-09-11",
            starts_at=time(10, 0),
            ends_at=time(9, 0),
        )


def test_grading_scale_rejects_invalid_range() -> None:
    with pytest.raises(ValidationError):
        GradingScaleCreate(
            code="BAD",
            name="Bad Scale",
            minimum_score=10,
            maximum_score=0,
        )


def test_m3_events_are_unique_and_namespaced() -> None:
    assert len(M3_EVENT_NAMES) == 10
    assert all("." in event for event in M3_EVENT_NAMES)
