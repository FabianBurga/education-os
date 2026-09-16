from pathlib import Path
from uuid import uuid4

from app.modules.integrations.schemas import (
    IntegrationRunEventMetadataRead,
    IntegrationRunEventRead,
    IntegrationRunItemRead,
    IntegrationRunRead,
)

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "app" / "modules" / "integrations" / "router.py"
SERVICE = ROOT / "app" / "modules" / "integrations" / "service.py"


def test_m24_run_read_models_are_typed_bounded_and_do_not_expose_raw_payloads():
    run = IntegrationRunRead(
        id=uuid4(), connector_id=uuid4(), connector_key="m24.csv", connector_display_name="CSV",
        mapping_id=None, initiated_by_user_id=uuid4(), source_kind="FILE", mode="DRY_RUN",
        source_filename="pilot.csv", source_fingerprint_sha256="a" * 64,
        connector_config_version=1, status="VALIDATED", total_rows=5, valid_rows=3,
        invalid_rows=1, conflict_rows=1, applied_rows=0, failed_rows=0, created_at="2026-01-01T00:00:00Z",
    )
    assert run.source_filename == "pilot.csv"
    assert run.total_rows == 5
    item = IntegrationRunItemRead(
        id=uuid4(), source_row_number=2, external_student_id="EXT-1",
        canonical_entity_type="STUDENT_ENROLLMENT", operation_class="CREATE", status="APPLIED",
        error_code=None, academic_period_code="2026", campus_id=uuid4(), student_code="ST-1",
        idempotency_key="b" * 64, student_profile_id=uuid4(), enrollment_id=uuid4(),
        created_at="2026-01-01T00:00:00Z",
    )
    assert item.enrollment_id is not None
    assert "detail" not in IntegrationRunItemRead.model_fields


def test_m24_event_read_model_filters_metadata_to_a_bounded_allowlist():
    event = IntegrationRunEventRead(
        sequence=1, event_type="CREATED", run_item_id=None, actor_user_id=uuid4(),
        created_at="2026-01-01T00:00:00Z",
        metadata=IntegrationRunEventMetadataRead(
            workflow="CSV_STUDENT_ENROLLMENT", source_filename="pilot.csv", source_sha256="c" * 64,
            total_rows=5, dry_run=True,
        ),
    )
    assert event.metadata.source_filename == "pilot.csv"
    assert "metadata_json" not in IntegrationRunEventRead.model_fields


def test_m24_run_read_routes_and_permission_gates_are_explicit_and_bounded():
    router = ROUTER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    assert "/runs/{run_id}/events" in router
    assert "le=100" in router
    assert "RUN_LIST_LIMIT = 100" in service
    assert "RUN_ITEM_LIMIT = 1000" in service
    assert "RUN_EVENT_LIMIT = 100" in service
    assert "require_integrations_view(session, principal)" in service
    assert "require_integrations_audit_read(session, principal)" in service
    assert "metadata_json" not in service.split("def list_run_events", maxsplit=1)[1].split("def apply_csv", maxsplit=1)[0]
