from uuid import uuid4

import pytest

from app.modules.events.service import enqueue_canonical_event


class CaptureSession:
    def __init__(self) -> None:
        self.items = []

    def add(self, item) -> None:
        self.items.append(item)


def test_enqueue_canonical_event_keeps_version_and_causality() -> None:
    session = CaptureSession()
    institution_id = uuid4()
    aggregate_id = uuid4()
    actor_user_id = uuid4()
    correlation_id = uuid4()
    causation_id = uuid4()

    event = enqueue_canonical_event(
        session,  # type: ignore[arg-type]
        institution_id=institution_id,
        event_type="attendance.recorded",
        event_version=2,
        aggregate_type="student",
        aggregate_id=aggregate_id,
        payload={"status": "ABSENT"},
        actor_user_id=actor_user_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata={"origin": "test"},
    )

    assert session.items == [event]
    assert event.institution_id == institution_id
    assert event.event_type == "attendance.recorded"
    assert event.aggregate_id == aggregate_id
    envelope = event.payload_json["_education_os_event"]
    assert envelope["version"] == 2
    assert envelope["actor_user_id"] == str(actor_user_id)
    assert envelope["correlation_id"] == str(correlation_id)
    assert envelope["causation_id"] == str(causation_id)
    assert envelope["metadata"] == {"origin": "test"}
    assert event.payload_json["data"] == {"status": "ABSENT"}


@pytest.mark.parametrize(
    ("event_type", "version"),
    [
        ("Attendance Recorded", 1),
        ("UPPERCASE.event", 1),
        ("a", 1),
        ("attendance.recorded", 0),
    ],
)
def test_enqueue_canonical_event_rejects_invalid_contracts(
    event_type: str,
    version: int,
) -> None:
    session = CaptureSession()

    with pytest.raises(ValueError):
        enqueue_canonical_event(
            session,  # type: ignore[arg-type]
            institution_id=uuid4(),
            event_type=event_type,
            event_version=version,
            aggregate_type="student",
            aggregate_id=uuid4(),
            payload={},
        )
