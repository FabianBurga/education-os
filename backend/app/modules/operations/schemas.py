from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReadinessCheck(BaseModel):
    code: str
    passed: bool
    detail: str


class PilotReadinessResult(BaseModel):
    run_id: UUID
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks: list[ReadinessCheck]
    executed_at: datetime


class PilotReadinessRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    institution_id: UUID
    executed_by_user_id: UUID | None
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    report_json: str
    executed_at: datetime


class PilotDataSummary(BaseModel):
    active_students: int
    active_guardians: int
    active_staff: int
    active_sections: int
    attendance_records: int
    grade_entries: int
    open_intelligence_signals: int
    open_automation_cases: int


class SecurityBaseline(BaseModel):
    runtime_role: str
    runtime_nosuperuser: bool
    runtime_nobypassrls: bool
    runtime_noinherit: bool
    critical_tables_total: int
    critical_tables_force_rls: int
    critical_tables_runtime_owned: int
