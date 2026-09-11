from uuid import UUID

from sqlmodel import Session

from app.modules.events.models import OutboxEvent


def enqueue_event(
    session: Session,
    *,
    institution_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict,
) -> OutboxEvent:
    event = OutboxEvent(
        institution_id=institution_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload_json=payload,
    )
    session.add(event)
    return event
