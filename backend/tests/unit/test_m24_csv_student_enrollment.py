from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.integrations.csv_student_enrollment import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    parse_csv_student_enrollment,
)
from app.modules.integrations.idempotency import integration_idempotency_key
from app.modules.integrations.models import IntegrationExternalStudentRef
from app.modules.integrations.schemas import IntegrationConnectorCreate

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0032_m24_csv_student_enrollment.py"
ROUTER = ROOT / "app" / "modules" / "integrations" / "router.py"
SERVICE = ROOT / "app" / "modules" / "integrations" / "service.py"

VALID = (
    "external_student_id,given_names,family_names,academic_period_code,campus_id\n"
    f"S-001,Ada,Lovelace,2026,{uuid4()}\n"
).encode()


def _code(payload: bytes) -> str:
    with pytest.raises(HTTPException) as raised:
        parse_csv_student_enrollment(payload)
    return raised.value.detail["code"]


def test_m24_csv_contract_parses_fixed_schema_and_normalizes_values():
    fingerprint, rows = parse_csv_student_enrollment(VALID)
    assert len(fingerprint) == 64
    assert len(rows) == 1
    assert rows[0].external_student_id == "S-001"
    assert rows[0].enrollment_status == "PENDING"
    assert rows[0].row_number == 2
    _, optional_rows = parse_csv_student_enrollment(
        (
            "external_student_id,given_names,family_names,academic_period_code,campus_id,student_code,"
            "enrollment_number,enrollment_status,enrolled_on\n"
            f"S-002,Grace,Hopper,2026,{uuid4()},ST-2,EN-2,ACTIVE,2026-01-01\n"
        ).encode()
    )
    assert optional_rows[0].enrollment_status == "ACTIVE"
    assert optional_rows[0].student_code == "ST-2"


def test_m24_csv_contract_fails_closed_for_schema_encoding_and_bounds():
    assert _code(b"external_student_id,given_names\nS-001,Ada\n") == "CSV_SCHEMA_INVALID"
    assert _code(
        b"external_student_id,given_names,family_names,academic_period_code,campus_id,unknown\n"
        + f"S-001,Ada,Lovelace,2026,{uuid4()},x\n".encode()
    ) == "CSV_SCHEMA_INVALID"
    assert _code(b"\xff\xfe") == "CSV_ENCODING_INVALID"
    assert _code(b"x" * (MAX_FILE_BYTES + 1)) == "CSV_TOO_LARGE"
    header = b"external_student_id,given_names,family_names,academic_period_code,campus_id\n"
    rows = b"".join(f"S-{i},Ada,Lovelace,2026,{uuid4()}\n".encode() for i in range(MAX_ROWS + 1))
    assert _code(header + rows) == "CSV_TOO_MANY_ROWS"
    overlong = b"S-001," + b"A" * 321 + b",Lovelace,2026," + str(uuid4()).encode() + b"\n"
    assert _code(header + overlong) == "CSV_ROW_INVALID"


def test_m24_csv_external_identity_is_tenant_qualified_and_immutable():
    assert IntegrationExternalStudentRef.__tablename__ == "integration_external_student_refs"
    for field in ("organization_id", "institution_id", "connector_id", "external_student_id", "student_profile_id", "created_run_id"):
        assert field in IntegrationExternalStudentRef.model_fields
    shared = dict(connector_id=str(uuid4()), external_source="csv:sha", source_record_identity="S-001", canonical_entity_type="STUDENT_ENROLLMENT", operation_class="CREATE")
    assert integration_idempotency_key(organization_id=str(uuid4()), institution_id=str(uuid4()), **shared) != integration_idempotency_key(organization_id=str(uuid4()), institution_id=str(uuid4()), **shared)


def test_m24_csv_connector_and_migration_only_allow_the_bounded_executable_workflow():
    connector = IntegrationConnectorCreate(connector_key="pilot.csv", connector_type="CSV_STUDENT_ENROLLMENT", display_name="Pilot")
    assert connector.connector_type == "CSV_STUDENT_ENROLLMENT"
    src = MIGRATION.read_text(encoding="utf-8")
    assert "integration_external_student_refs" in src
    assert "ENABLE ROW LEVEL SECURITY" in src
    assert "FORCE ROW LEVEL SECURITY" in src
    assert "GRANT SELECT, INSERT" in src
    assert "ITEM_APPLIED" in src and "ITEM_FAILED" in src
    assert "UPDATE" not in src.split("def downgrade", maxsplit=1)[0]


def test_m24_csv_routes_are_explicit_and_apply_uses_canonical_services_only():
    router = ROUTER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    assert "/connectors/{connector_id}/csv/student-enrollment/preview" in router
    assert "/runs/{run_id}/apply" in router
    assert "/runs/{run_id}/items" in router
    assert "create_student_profile" in service
    assert "create_enrollment_record" in service
    assert "enqueue_canonical_event" not in service
    assert "begin_nested" in service
