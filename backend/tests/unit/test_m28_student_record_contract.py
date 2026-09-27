from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.students.router import StudentCreate, StudentUpdate

ROOT = Path(__file__).resolve().parents[2]


def test_student_mutation_schemas_reject_server_controlled_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        StudentCreate.model_validate({"person_id": "00000000-0000-0000-0000-000000000001", "institution_id": "00000000-0000-0000-0000-000000000002"})
    with pytest.raises(ValidationError):
        StudentUpdate.model_validate({"status": "ACTIVE", "organization_id": "00000000-0000-0000-0000-000000000002", "expected_updated_at": "2026-01-01T00:00:00Z"})
    with pytest.raises(ValidationError):
        StudentUpdate.model_validate({"status": "ACTIVE"})


def test_student_routes_and_service_enforce_effective_permission_and_tenant_scope() -> None:
    router = (ROOT / "app/modules/students/router.py").read_text(encoding="utf-8")
    service = (ROOT / "app/modules/students/service.py").read_text(encoding="utf-8")
    access = (ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert '"students.read"' in router
    assert '"students.manage"' in router
    assert "principal.organization_id" in router and "principal.institution_id" in router
    assert "require_student_record_permission" in service
    assert "_permission_exists(session, principal, permission_key)" in access
    assert "role.key" not in service


def test_student_mutations_append_audit_and_canonical_event_in_same_session() -> None:
    service = (ROOT / "app/modules/students/service.py").read_text(encoding="utf-8")
    assert "record_audit(" in service
    assert "enqueue_canonical_event(" in service
    assert 'event_type="student.profile.created"' in service
    assert 'event_type="student.profile.updated"' in service
    assert "session.commit()" not in service
    assert "with session.begin_nested()" in service


def test_permission_migration_is_forward_only_and_does_not_auto_grant_roles() -> None:
    migration = ROOT / "alembic/versions/0043_m28_student_record_permissions.py"
    source = migration.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0042_m27_true_recurrence"' in source
    assert "students.read" in source and "students.manage" in source and "enrollments.manage" in source
    assert "INSERT INTO role_permissions" not in source
    assert len("0043_m28_student_record_perms") <= 32
