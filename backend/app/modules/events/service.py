import re
from uuid import UUID

from sqlmodel import Session

from app.modules.events.models import OutboxEvent

_CANONICAL_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,179}$")
_ENVELOPE_KEY = "_education_os_event"


def enqueue_event(
    session: Session,
    *,
    institution_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict,
) -> OutboxEvent:
    """Backward-compatible M0-M17 transactional outbox helper."""
    event = OutboxEvent(
        institution_id=institution_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload_json=payload,
    )
    session.add(event)
    return event


def enqueue_canonical_event(
    session: Session,
    *,
    institution_id: UUID,
    event_type: str,
    event_version: int,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict,
    actor_user_id: UUID | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    metadata: dict | None = None,
) -> OutboxEvent:
    """M18+ canonical event without changing the frozen outbox table schema."""
    if not _CANONICAL_EVENT_TYPE_RE.fullmatch(event_type):
        raise ValueError(
            "event_type must match ^[a-z][a-z0-9_.-]{2,179}$"
        )
    if event_version < 1:
        raise ValueError("event_version must be >= 1")
    if not aggregate_type.strip():
        raise ValueError("aggregate_type is required")

    envelope = {
        "version": event_version,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "correlation_id": str(correlation_id) if correlation_id else None,
        "causation_id": str(causation_id) if causation_id else None,
        "metadata": metadata or {},
    }
    event = OutboxEvent(
        institution_id=institution_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload_json={
            _ENVELOPE_KEY: envelope,
            "data": payload,
        },
    )
    session.add(event)
    return event
