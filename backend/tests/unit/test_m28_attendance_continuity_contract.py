from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.attendance.schemas import AttendanceExpectedState, AttendanceRecordUpsert
from app.modules.attendance.service import (
    _expected_empty_state,
    require_attendance_permission,
)
from app.modules.student_timeline.projector import EVENT_SPECS


def test_first_offline_attendance_write_accepts_an_explicit_empty_base():
    empty = AttendanceExpectedState(
        attendance_record_id=None,
        attendance_code_id=None,
        minutes_late=0,
        note=None,
    )

    assert _expected_empty_state(empty)
    assert not _expected_empty_state(
        empty.model_copy(update={"minutes_late": 1})
    )


def test_attendance_write_contract_rejects_server_owned_fields():
    with pytest.raises(ValidationError):
        AttendanceRecordUpsert(
            student_section_assignment_id=uuid4(),
            attendance_code_id=uuid4(),
            institution_id=uuid4(),
        )


def test_m21_consumes_canonical_attendance_facts_not_sync_activity():
    assert EVENT_SPECS["student.attendance.recorded"].category == "ATTENDANCE"
    assert EVENT_SPECS["student.attendance.updated"].category == "ATTENDANCE"
    assert "teacher.attendance.synced" not in EVENT_SPECS


class _PermissionResult:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _PermissionSession:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.params = None

    def exec(self, statement, *, params):
        self.statement = str(statement)
        self.params = params
        return _PermissionResult(self.row)


def test_attendance_permission_uses_principal_tenant_and_effective_role_grant():
    principal = SimpleNamespace(
        user_id=uuid4(), organization_id=uuid4(), institution_id=uuid4()
    )
    session = _PermissionSession((1,))

    require_attendance_permission(session, principal, "attendance.correct")

    assert session.params == {
        "user_id": principal.user_id,
        "organization_id": principal.organization_id,
        "institution_id": principal.institution_id,
        "permission": "attendance.correct",
    }
    assert "m.status='ACTIVE'" in session.statement
    assert "r.institution_id=m.institution_id" in session.statement
    assert "i.organization_id=:organization_id" in session.statement


def test_attendance_permission_denies_missing_grant_without_role_fallback():
    principal = SimpleNamespace(
        user_id=uuid4(), organization_id=uuid4(), institution_id=uuid4()
    )

    with pytest.raises(HTTPException) as error:
        require_attendance_permission(
            _PermissionSession(None), principal, "attendance.manage"
        )

    assert error.value.status_code == 403
