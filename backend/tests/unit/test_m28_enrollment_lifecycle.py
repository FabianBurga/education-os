from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.enrollment.router import EnrollmentCreate, EnrollmentStatusUpdate
from app.modules.enrollment.service import available_enrollment_actions

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("PENDING", ["ACTIVE", "CANCELLED"]),
        ("ACTIVE", ["COMPLETED", "WITHDRAWN"]),
        ("WITHDRAWN", ["ACTIVE"]),
        ("COMPLETED", []),
        ("CANCELLED", []),
        ("TRANSFERRED", []),
    ],
)
def test_enrollment_actions_are_closed_and_bounded(current: str, expected: list[str]) -> None:
    assert available_enrollment_actions(SimpleNamespace(status=current)) == expected


def test_enrollment_commands_reject_mass_assignment_and_transfer_state() -> None:
    with pytest.raises(ValidationError):
        EnrollmentCreate.model_validate({
            "student_profile_id": "00000000-0000-0000-0000-000000000001",
            "academic_period_id": "00000000-0000-0000-0000-000000000002",
            "campus_id": "00000000-0000-0000-0000-000000000003",
            "organization_id": "00000000-0000-0000-0000-000000000004",
        })
    with pytest.raises(ValidationError):
        EnrollmentStatusUpdate.model_validate({
            "status": "TRANSFERRED",
            "expected_updated_at": datetime.now(UTC).isoformat(),
        })


def test_transition_requires_expected_revision_and_bounded_reason_code() -> None:
    with pytest.raises(ValidationError):
        EnrollmentStatusUpdate.model_validate({"status": "WITHDRAWN"})
    with pytest.raises(ValidationError):
        EnrollmentStatusUpdate.model_validate({
            "status": "WITHDRAWN",
            "expected_updated_at": datetime.now(UTC).isoformat(),
            "reason_code": "not a bounded code",
        })


def test_enrollment_read_permission_migration_is_forward_only_and_has_no_role_grants() -> None:
    migration = (ROOT / "alembic/versions/0044_m28_enrollment_read.py").read_text(encoding="utf-8")
    assert 'revision: str = "0044_m28_enrollment_read"' in migration
    assert 'down_revision: str | None = "0043_m28_student_record_perms"' in migration
    assert "enrollments.read" in migration
    assert "INSERT INTO role_permissions" not in migration
