from uuid import UUID

from sqlmodel import Session

from app.modules.audit.models import AuditLog


def record_audit(
    session: Session,
    *,
    institution_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        institution_id=institution_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata or {},
    )
    session.add(entry)
    return entry
