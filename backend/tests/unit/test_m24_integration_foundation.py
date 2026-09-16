from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.integrations.idempotency import integration_idempotency_key
from app.modules.integrations.models import (
    IntegrationConnector,
    IntegrationMapping,
    IntegrationRun,
    IntegrationRunEvent,
    IntegrationRunItem,
)
from app.modules.integrations.schemas import IntegrationConnectorCreate

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0031_m24_integration_foundation.py"
ROUTER = ROOT / "app" / "modules" / "integrations" / "router.py"
SERVICE = ROOT / "app" / "modules" / "integrations" / "service.py"


def test_m24_foundation_models_have_frozen_table_names_and_identities():
    assert IntegrationConnector.__tablename__ == "integration_connectors"
    assert IntegrationMapping.__tablename__ == "integration_mappings"
    assert IntegrationRun.__tablename__ == "integration_runs"
    assert IntegrationRunItem.__tablename__ == "integration_run_items"
    assert IntegrationRunEvent.__tablename__ == "integration_run_events"
    for model in (IntegrationConnector, IntegrationMapping, IntegrationRun, IntegrationRunItem, IntegrationRunEvent):
        assert "organization_id" in model.model_fields
        assert "institution_id" in model.model_fields
        assert "id" in model.model_fields


def test_m24_idempotency_is_deterministic_tenant_qualified_and_collision_sensitive():
    connector_id = str(uuid4())
    base = dict(connector_id=connector_id, external_source="file:sha256", source_record_identity="row:7", canonical_entity_type="STUDENT", operation_class="CREATE")
    first_org, first_institution = str(uuid4()), str(uuid4())
    second_org, second_institution = str(uuid4()), str(uuid4())
    first = integration_idempotency_key(organization_id=first_org, institution_id=first_institution, **base)
    second = integration_idempotency_key(organization_id=second_org, institution_id=second_institution, **base)
    repeat = integration_idempotency_key(organization_id=second_org, institution_id=second_institution, **base)
    assert len(first) == 64
    assert second == repeat
    assert first != second


def test_m24_connector_schema_rejects_secret_material_and_non_csv_connectors():
    with pytest.raises(ValidationError):
        IntegrationConnectorCreate(connector_key="pilot.csv", connector_type="FILE_CSV", display_name="Pilot", configuration={"api_key": "nope"})
    with pytest.raises(ValidationError):
        IntegrationConnectorCreate(connector_key="pilot.rest", connector_type="REST", display_name="Pilot")


def test_m24_migration_enforces_lifecycles_rls_and_least_privilege_runtime_grants():
    src = MIGRATION.read_text(encoding="utf-8")
    for table in ("integration_connectors", "integration_mappings", "integration_runs", "integration_run_items", "integration_run_events"):
        assert f'"{table}"' in src
    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "FORCE ROW LEVEL SECURITY" in src
    assert "{table}_select" in src
    assert "status IN ('ENABLED','DISABLED')" in src
    assert "('CREATED','VALIDATING','VALIDATED','APPLYING','COMPLETED','FAILED','CANCELLED')" in src
    assert "('PENDING','VALID','INVALID','APPLIED','CONFLICT','FAILED')" in src
    assert '"SELECT, INSERT, UPDATE"' in src
    assert '"SELECT, INSERT"' in src
    assert "integration_credentials" not in src
    assert "DELETE" not in src.split("def downgrade", maxsplit=1)[0]


def test_m24_api_is_permission_gated_and_does_not_expose_execution_or_secret_routes():
    router = ROUTER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    for path in ("/connectors", "/connectors/{connector_id}/disable", "/connectors/{connector_id}/enable", "/runs"):
        assert path in router
    for forbidden in ("upload", "webhook", "credentials", "execute", "callback"):
        assert forbidden not in router.lower()
    assert "require_integrations_view" in service
    assert "require_integrations_manage" in service
    assert "Integration connector not found" in service
