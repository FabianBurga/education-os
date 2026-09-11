from sqlmodel import SQLModel

from app.modules.audit.models import AuditLog  # noqa: F401


def test_audit_foreign_key_targets_are_registered() -> None:
    assert "audit_logs" in SQLModel.metadata.tables
    assert "institutions" in SQLModel.metadata.tables
    assert "user_accounts" in SQLModel.metadata.tables
