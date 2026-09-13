from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.teacher_console.schemas import (
    TeacherAttendanceCode,
    TeacherAttendanceMark,
    TeacherAttendanceRow,
    TeacherClassRead,
    TeacherClassSession,
    TeacherRosterStudent,
)


class TeacherOfflineSessionSnapshot(BaseModel):
    session: TeacherClassSession
    attendance: list[TeacherAttendanceRow]

class TeacherOfflineClassSnapshot(BaseModel):
    classroom: TeacherClassRead
    roster: list[TeacherRosterStudent]
    sessions: list[TeacherOfflineSessionSnapshot]

class TeacherOfflineSnapshot(BaseModel):
    snapshot_version: int = 1
    generated_at: datetime
    expires_at: datetime
    days: int
    classes: list[TeacherOfflineClassSnapshot]
    attendance_codes: list[TeacherAttendanceCode]

class TeacherOfflineAttendanceBase(BaseModel):
    attendance_record_id: UUID | None = None
    attendance_code_id: UUID | None = None
    minutes_late: int = Field(default=0, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=500)

class TeacherOfflineAttendanceState(TeacherOfflineAttendanceBase):
    pass

class TeacherOfflineAttendanceOperation(BaseModel):
    operation_id: UUID
    operation_type: Literal["ATTENDANCE_MARK"] = "ATTENDANCE_MARK"
    class_session_id: UUID
    base: TeacherOfflineAttendanceBase
    desired: TeacherAttendanceMark

class TeacherOfflineSyncBatch(BaseModel):
    operations: list[TeacherOfflineAttendanceOperation] = Field(min_length=1, max_length=100)
    @model_validator(mode="after")
    def validate_batch(self):
        ids=[x.operation_id for x in self.operations]
        if len(ids)!=len(set(ids)):
            raise ValueError("operation_id values must be unique inside a batch")
        targets=[(x.class_session_id,x.desired.student_section_assignment_id) for x in self.operations]
        if len(targets)!=len(set(targets)):
            raise ValueError("Only one attendance operation per session/student target is allowed")
        return self

class TeacherOfflineSyncResult(BaseModel):
    operation_id: UUID
    status: Literal["APPLIED","REPLAYED","CONFLICT","IDEMPOTENCY_MISMATCH","REJECTED"]
    result_entity_id: UUID | None = None
    server_state: TeacherOfflineAttendanceState | None = None
    detail: str | None = None

class TeacherOfflineSyncResponse(BaseModel):
    results: list[TeacherOfflineSyncResult]
