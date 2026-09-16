from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.deps import CurrentPrincipal
from app.modules.audit.service import record_audit
from app.modules.integrations.access import (
    require_integrations_manage,
    require_integrations_view,
)
from app.modules.integrations.models import IntegrationConnector
from app.modules.integrations.schemas import (
    IntegrationConnectorCreate,
    IntegrationConnectorRead,
    IntegrationRunRead,
)


def _connector_read(connector: IntegrationConnector) -> IntegrationConnectorRead:
    return IntegrationConnectorRead(
        id=connector.id, connector_key=connector.connector_key, connector_type=connector.connector_type,
        display_name=connector.display_name, status=connector.status, config_version=connector.config_version,
        configuration=connector.configuration_json, created_at=connector.created_at, updated_at=connector.updated_at,
    )


def create_connector(session: Session, principal: CurrentPrincipal, payload: IntegrationConnectorCreate) -> IntegrationConnectorRead:
    require_integrations_manage(session, principal)
    connector = IntegrationConnector(
        organization_id=principal.organization_id, institution_id=principal.institution_id,
        connector_key=payload.connector_key, connector_type=payload.connector_type,
        display_name=payload.display_name, configuration_json=payload.configuration,
        created_by_user_id=principal.user_id,
    )
    session.add(connector)
    session.flush()
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action="INTEGRATION_CONNECTOR_CREATED", entity_type="IntegrationConnector", entity_id=connector.id,
                 metadata={"connector_key": connector.connector_key, "connector_type": connector.connector_type})
    return _connector_read(connector)


def list_connectors(session: Session, principal: CurrentPrincipal) -> list[IntegrationConnectorRead]:
    require_integrations_view(session, principal)
    return [_connector_read(item) for item in session.exec(select(IntegrationConnector).order_by(IntegrationConnector.created_at.desc())).all()]


def get_connector(session: Session, principal: CurrentPrincipal, connector_id: UUID) -> IntegrationConnectorRead:
    require_integrations_view(session, principal)
    connector = session.get(IntegrationConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connector not found")
    return _connector_read(connector)


def set_connector_status(session: Session, principal: CurrentPrincipal, connector_id: UUID, target: str) -> IntegrationConnectorRead:
    require_integrations_manage(session, principal)
    connector = session.get(IntegrationConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration connector not found")
    connector.status = target
    connector.config_version += 1
    session.add(connector)
    record_audit(session, institution_id=principal.institution_id, actor_user_id=principal.user_id,
                 action=f"INTEGRATION_CONNECTOR_{target}", entity_type="IntegrationConnector", entity_id=connector.id,
                 metadata={"connector_key": connector.connector_key, "config_version": connector.config_version})
    return _connector_read(connector)


def list_runs(session: Session, principal: CurrentPrincipal) -> list[IntegrationRunRead]:
    require_integrations_view(session, principal)
    rows = session.exec(text("""
        SELECT r.id, r.connector_id, r.mapping_id, r.initiated_by_user_id, r.source_kind, r.mode,
               r.source_fingerprint_sha256, r.idempotency_key, r.connector_config_version,
               COALESCE((SELECT e.event_type FROM integration_run_events e WHERE e.run_id=r.id
                         ORDER BY e.sequence DESC LIMIT 1), 'CREATED'), r.created_at
        FROM integration_runs r ORDER BY r.created_at DESC
    """)).all()
    return [IntegrationRunRead(id=row[0], connector_id=row[1], mapping_id=row[2], initiated_by_user_id=row[3],
                               source_kind=row[4], mode=row[5], source_fingerprint_sha256=row[6], idempotency_key=row[7],
                               connector_config_version=int(row[8]), status=row[9], created_at=row[10]) for row in rows]


def get_run(session: Session, principal: CurrentPrincipal, run_id: UUID) -> IntegrationRunRead:
    for run in list_runs(session, principal):
        if run.id == run_id:
            return run
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration run not found")
