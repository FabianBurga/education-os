from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal


@dataclass(frozen=True, slots=True)
class AgentContextEnvelope:
    actor_user_id: UUID
    organization_id: UUID
    institution_id: UUID
    effective_permissions: frozenset[str]
    agent_key: str
    request_type: str
    authorized_entity_id: UUID | None
    correlation_id: UUID


def build_context_envelope(
    session: Session,
    principal: CurrentPrincipal,
    *,
    agent_key: str,
    request_type: str,
    entity_id: UUID | None,
) -> AgentContextEnvelope:
    rows = session.exec(text("""
        SELECT DISTINCT p.key
        FROM memberships m
        JOIN membership_roles mr ON mr.membership_id = m.id
        JOIN role_permissions rp ON rp.role_id = mr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE m.user_id = CAST(:user_id AS uuid)
          AND m.institution_id = CAST(:institution_id AS uuid)
          AND m.status = 'ACTIVE'
    """), params={"user_id": str(principal.user_id), "institution_id": str(principal.institution_id)}).all()
    return AgentContextEnvelope(
        actor_user_id=principal.user_id, organization_id=principal.organization_id,
        institution_id=principal.institution_id, effective_permissions=frozenset(str(row[0]) for row in rows),
        agent_key=agent_key, request_type=request_type, authorized_entity_id=entity_id,
        correlation_id=uuid4(),
    )
