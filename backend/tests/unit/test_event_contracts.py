from uuid import uuid4

from app.modules.events.models import OutboxEvent


def test_event_type_is_versioned():
    event = OutboxEvent(
        institution_id=uuid4(),
        event_type="foundation.test.v1",
        aggregate_type="test",
        aggregate_id=uuid4(),
        payload_json={},
    )
    assert event.event_type.endswith(".v1")
    assert event.status == "PENDING"
