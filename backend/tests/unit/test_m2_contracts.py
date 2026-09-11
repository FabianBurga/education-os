from datetime import time

import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.academics.schemas import ScheduleSlotCreate, SectionCreate
from app.modules.m2_events import M2_EVENT_NAMES


def test_m2_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/academics/levels",
        "/api/v1/academics/grades",
        "/api/v1/academics/subjects",
        "/api/v1/academics/sections",
        "/api/v1/academics/curriculum-plans",
        "/api/v1/academics/curriculum-plans/{plan_id}/subjects",
        "/api/v1/academics/course-offerings",
        "/api/v1/academics/teaching-assignments",
        "/api/v1/academics/student-section-assignments",
        "/api/v1/academics/schedule-slots",
    }
    assert expected.issubset(paths)


def test_schedule_slot_rejects_invalid_time_range() -> None:
    with pytest.raises(ValidationError):
        ScheduleSlotCreate(
            course_offering_id="11111111-1111-1111-1111-111111111111",
            weekday=1,
            starts_at=time(10, 0),
            ends_at=time(9, 0),
        )


def test_section_capacity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        SectionCreate(
            academic_period_id="11111111-1111-1111-1111-111111111111",
            campus_id="22222222-2222-2222-2222-222222222222",
            grade_level_id="33333333-3333-3333-3333-333333333333",
            code="A",
            name="A",
            capacity=0,
        )


def test_m2_event_names_are_unique_and_namespaced() -> None:
    assert len(M2_EVENT_NAMES) == 10
    assert all("." in event for event in M2_EVENT_NAMES)
