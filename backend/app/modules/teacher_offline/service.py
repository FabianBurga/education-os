from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import TeacherPrincipal
from app.modules.attendance.schemas import AttendanceExpectedState, AttendanceRecordUpsert
from app.modules.attendance.service import apply_attendance_record
from app.modules.audit.service import record_audit
from app.modules.events.service import enqueue_canonical_event
from app.modules.teacher_console.service import (
    attendance_rows,
    list_attendance_codes,
    list_class_sessions,
    list_roster,
    list_teacher_classes,
)
from app.modules.teacher_offline.schemas import (
    TeacherOfflineAttendanceBase,
    TeacherOfflineAttendanceOperation,
    TeacherOfflineAttendanceState,
    TeacherOfflineClassSnapshot,
    TeacherOfflineSessionSnapshot,
    TeacherOfflineSnapshot,
    TeacherOfflineSyncBatch,
    TeacherOfflineSyncResponse,
    TeacherOfflineSyncResult,
)

CAPABILITY_KEY="teacher.offline_pwa"
SNAPSHOT_TTL_HOURS=24


def _require_capability(session: Session, principal: TeacherPrincipal) -> None:
    row=session.exec(text("""SELECT enabled FROM institution_capabilities WHERE institution_id=CAST(:institution_id AS uuid) AND capability_key=:capability_key"""), params={"institution_id":str(principal.institution_id),"capability_key":CAPABILITY_KEY}).first()
    if row is None or not bool(row[0]):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Teacher offline PWA capability is disabled")


def teacher_offline_snapshot(session: Session, principal: TeacherPrincipal, *, days: int) -> TeacherOfflineSnapshot:
    _require_capability(session, principal)
    db_today=session.exec(text("SELECT CURRENT_DATE")).one()[0]
    window_start=db_today-timedelta(days=days)
    window_end=db_today+timedelta(days=1)
    classes=list_teacher_classes(session, principal)
    codes=list_attendance_codes(session, principal)
    result=[]
    for classroom in classes:
        roster=list_roster(session, principal, classroom.course_offering_id)
        sessions=[
            x
            for x in list_class_sessions(session, principal, classroom.course_offering_id)
            if x.status == "OPEN" and window_start <= x.session_date <= window_end
        ]
        result.append(TeacherOfflineClassSnapshot(classroom=classroom, roster=roster, sessions=[TeacherOfflineSessionSnapshot(session=x, attendance=attendance_rows(session, principal, x.id)) for x in sessions]))
    generated=datetime.now(UTC)
    return TeacherOfflineSnapshot(generated_at=generated, expires_at=generated+timedelta(hours=SNAPSHOT_TTL_HOURS), days=days, classes=result, attendance_codes=codes)


def _hash(operation: TeacherOfflineAttendanceOperation) -> str:
    raw=json.dumps(operation.model_dump(mode="json"),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _state(row) -> TeacherOfflineAttendanceState:
    if row is None:
        return TeacherOfflineAttendanceState(attendance_record_id=None,attendance_code_id=None,minutes_late=0,note=None)
    return TeacherOfflineAttendanceState(attendance_record_id=row[0],attendance_code_id=row[1],minutes_late=int(row[2] or 0),note=row[3])


def _same(base: TeacherOfflineAttendanceBase, current: TeacherOfflineAttendanceState) -> bool:
    return base.attendance_record_id==current.attendance_record_id and base.attendance_code_id==current.attendance_code_id and int(base.minutes_late or 0)==int(current.minutes_late or 0) and base.note==current.note


def _sync_lock_keys(
    principal: TeacherPrincipal,
    operations: list[TeacherOfflineAttendanceOperation],
) -> list[str]:
    """Return every idempotency and target lock in one deterministic order."""
    keys: set[str] = set()
    for operation in operations:
        keys.add(
            "teacher-offline:operation:"
            f"{principal.institution_id}:{principal.user_id}:{operation.operation_id}"
        )
        keys.add(
            "teacher-offline:target:"
            f"{principal.institution_id}:{operation.class_session_id}:"
            f"{operation.desired.student_section_assignment_id}"
        )
    return sorted(keys)


def _acquire_sync_locks(
    session: Session,
    principal: TeacherPrincipal,
    operations: list[TeacherOfflineAttendanceOperation],
) -> None:
    # All locks are acquired before reading receipts or attendance state. The
    # global lexical order prevents cross-batch deadlocks, while target locks
    # prevent two distinct operation IDs from overwriting the same student.
    for key in _sync_lock_keys(principal, operations):
        session.exec(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            params={"key": key},
        ).one()


def _receipt(session: Session, principal: TeacherPrincipal, operation_id: UUID):
    return session.exec(text("""SELECT request_sha256,result_entity_id FROM teacher_offline_receipts WHERE institution_id=CAST(:institution_id AS uuid) AND actor_user_id=CAST(:actor_user_id AS uuid) AND operation_id=CAST(:operation_id AS uuid)"""),params={"institution_id":str(principal.institution_id),"actor_user_id":str(principal.user_id),"operation_id":str(operation_id)}).first()


def _section(session: Session, principal: TeacherPrincipal, class_session_id: UUID) -> UUID:
    row=session.exec(text("""SELECT cs.section_id FROM class_sessions cs
      JOIN teaching_assignments ta ON ta.course_offering_id=cs.course_offering_id
        AND ta.staff_profile_id=CAST(:staff_profile_id AS uuid)
        AND ta.organization_id=CAST(:organization_id AS uuid)
        AND ta.institution_id=CAST(:institution_id AS uuid)
      WHERE cs.id=CAST(:class_session_id AS uuid)
        AND cs.organization_id=CAST(:organization_id AS uuid)
        AND cs.institution_id=CAST(:institution_id AS uuid)
        AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE)
        AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
        AND (ta.starts_on IS NULL OR ta.starts_on<=cs.session_date)
        AND (ta.ends_on IS NULL OR ta.ends_on>=cs.session_date)
      LIMIT 1"""),params={"staff_profile_id":str(principal.staff_profile_id),"class_session_id":str(class_session_id),"organization_id":str(principal.organization_id),"institution_id":str(principal.institution_id)}).first()
    if row is None:
        raise HTTPException(status_code=403,detail="Class session is outside the current teacher scope")
    return row[0]


def _assert_target(session: Session, principal: TeacherPrincipal, class_session_id: UUID, section_id: UUID, assignment_id: UUID) -> None:
    row=session.exec(text("""SELECT 1
      FROM class_sessions cs
      JOIN course_offerings co ON co.id=cs.course_offering_id
        AND co.organization_id=cs.organization_id AND co.institution_id=cs.institution_id
      JOIN academic_periods ap ON ap.id=co.academic_period_id
        AND ap.organization_id=cs.organization_id AND ap.institution_id=cs.institution_id
      JOIN sections sec ON sec.id=cs.section_id
        AND sec.organization_id=cs.organization_id AND sec.institution_id=cs.institution_id
      JOIN student_section_assignments ssa ON ssa.section_id=sec.id
        AND ssa.academic_period_id=co.academic_period_id
        AND ssa.organization_id=cs.organization_id AND ssa.institution_id=cs.institution_id
      JOIN enrollments e ON e.id=ssa.enrollment_id
        AND e.organization_id=ssa.organization_id AND e.institution_id=ssa.institution_id
      JOIN student_profiles sp ON sp.id=e.student_profile_id
        AND sp.organization_id=e.organization_id AND sp.institution_id=e.institution_id
      WHERE cs.id=CAST(:session_id AS uuid)
        AND cs.section_id=CAST(:section AS uuid)
        AND cs.organization_id=CAST(:organization_id AS uuid)
        AND cs.institution_id=CAST(:institution_id AS uuid)
        AND co.status='ACTIVE' AND ap.status='ACTIVE'
        AND sec.status='ACTIVE'
        AND cs.session_date BETWEEN ap.starts_on AND ap.ends_on
        AND ssa.id=CAST(:assignment AS uuid)
        AND ssa.status IN ('ACTIVE','TRANSFERRED')
        AND ssa.assigned_on<=cs.session_date
        AND (ssa.ended_on IS NULL OR ssa.ended_on>=cs.session_date)
        AND e.status='ACTIVE' AND e.campus_id=sec.campus_id
        AND sp.status='ACTIVE'
      LIMIT 1"""),params={"session_id":str(class_session_id),"assignment":str(assignment_id),"section":str(section_id),"organization_id":str(principal.organization_id),"institution_id":str(principal.institution_id)}).first()
    if row is None:
        raise HTTPException(status_code=403,detail="Student is outside the current class session roster")


def _current(session: Session, class_session_id: UUID, assignment_id: UUID) -> TeacherOfflineAttendanceState:
    row=session.exec(text("""SELECT id,attendance_code_id,minutes_late,note FROM attendance_records WHERE class_session_id=CAST(:session AS uuid) AND student_section_assignment_id=CAST(:assignment AS uuid)"""),params={"session":str(class_session_id),"assignment":str(assignment_id)}).first()
    return _state(row)


def _by_id(session: Session, record_id: UUID):
    row=session.exec(text("SELECT id,attendance_code_id,minutes_late,note FROM attendance_records WHERE id=CAST(:id AS uuid)"),params={"id":str(record_id)}).first()
    return _state(row) if row is not None else None


def _insert_receipt(session: Session, principal: TeacherPrincipal, op: TeacherOfflineAttendanceOperation, request_hash: str, record_id: UUID) -> None:
    session.exec(text("""INSERT INTO teacher_offline_receipts (id,organization_id,institution_id,actor_user_id,operation_id,operation_type,request_sha256,result_entity_id,status,created_at) VALUES (CAST(:id AS uuid),CAST(:org AS uuid),CAST(:inst AS uuid),CAST(:actor AS uuid),CAST(:operation AS uuid),'ATTENDANCE_MARK',:hash,CAST(:record AS uuid),'APPLIED',NOW())"""),params={"id":str(uuid4()),"org":str(principal.organization_id),"inst":str(principal.institution_id),"actor":str(principal.user_id),"operation":str(op.operation_id),"hash":request_hash,"record":str(record_id)})


def _sync_one(session: Session, principal: TeacherPrincipal, op: TeacherOfflineAttendanceOperation) -> TeacherOfflineSyncResult:
    request_hash=_hash(op)
    try:
        section_id=_section(session,principal,op.class_session_id)
        _assert_target(session,principal,op.class_session_id,section_id,op.desired.student_section_assignment_id)
    except HTTPException as exc:
        return TeacherOfflineSyncResult(operation_id=op.operation_id,status="REJECTED",detail=str(exc.detail))
    receipt=_receipt(session,principal,op.operation_id)
    if receipt is not None:
        if receipt[0]!=request_hash:
            return TeacherOfflineSyncResult(operation_id=op.operation_id,status="IDEMPOTENCY_MISMATCH",result_entity_id=receipt[1],server_state=_by_id(session,receipt[1]),detail="operation_id was already applied with a different payload")
        return TeacherOfflineSyncResult(operation_id=op.operation_id,status="REPLAYED",result_entity_id=receipt[1],server_state=_by_id(session,receipt[1]))
    code=session.exec(text("""SELECT 1 FROM attendance_codes WHERE id=CAST(:id AS uuid)
      AND organization_id=CAST(:organization_id AS uuid)
      AND institution_id=CAST(:institution_id AS uuid) AND status='ACTIVE' LIMIT 1"""),params={"id":str(op.desired.attendance_code_id),"organization_id":str(principal.organization_id),"institution_id":str(principal.institution_id)}).first()
    if code is None:
        return TeacherOfflineSyncResult(operation_id=op.operation_id,status="REJECTED",detail="Attendance code is not active in the current institution")
    current=_current(session,op.class_session_id,op.desired.student_section_assignment_id)
    if not _same(op.base,current):
        return TeacherOfflineSyncResult(operation_id=op.operation_id,status="CONFLICT",result_entity_id=current.attendance_record_id,server_state=current,detail="Server attendance changed after the offline snapshot; explicit teacher resolution is required")
    try:
        mutation=apply_attendance_record(
            session,
            principal,
            op.class_session_id,
            AttendanceRecordUpsert(
                student_section_assignment_id=op.desired.student_section_assignment_id,
                attendance_code_id=op.desired.attendance_code_id,
                minutes_late=op.desired.minutes_late,
                note=op.desired.note,
            ),
            expected_state=AttendanceExpectedState(**op.base.model_dump()),
            correction_reason="OFFLINE_RECONCILIATION",
            source="teacher_offline_pwa",
            correlation_id=op.operation_id,
            teacher_scope_required=True,
            commit=False,
        )
    except HTTPException as exc:
        return TeacherOfflineSyncResult(operation_id=op.operation_id,status="REJECTED",detail=str(exc.detail))
    record=mutation.record
    record_id=record.id
    record_audit(session,institution_id=principal.institution_id,actor_user_id=principal.user_id,action="TEACHER_OFFLINE_ATTENDANCE_SYNCED",entity_type="AttendanceRecord",entity_id=record_id,metadata={"operation_id":str(op.operation_id),"source":"teacher_offline_pwa"})
    enqueue_canonical_event(session,institution_id=principal.institution_id,event_type="teacher.attendance.synced",event_version=1,aggregate_type="attendance_record",aggregate_id=record_id,actor_user_id=principal.user_id,correlation_id=op.operation_id,payload={"operation_id":str(op.operation_id),"class_session_id":str(op.class_session_id),"student_section_assignment_id":str(op.desired.student_section_assignment_id),"attendance_code_id":str(op.desired.attendance_code_id),"minutes_late":op.desired.minutes_late},metadata={"source":"teacher_offline_pwa","privacy":"note_excluded"})
    _insert_receipt(session,principal,op,request_hash,record_id)
    session.flush()
    result_state=TeacherOfflineAttendanceState(attendance_record_id=record_id,attendance_code_id=record.attendance_code_id,minutes_late=record.minutes_late,note=record.note)
    return TeacherOfflineSyncResult(operation_id=op.operation_id,status="APPLIED",result_entity_id=record_id,server_state=result_state)


def sync_teacher_offline_operations(
    session: Session,
    principal: TeacherPrincipal,
    payload: TeacherOfflineSyncBatch,
    *,
    commit: bool = True,
) -> TeacherOfflineSyncResponse:
    _require_capability(session,principal)
    _acquire_sync_locks(session, principal, payload.operations)
    ordered=sorted(payload.operations,key=lambda x:str(x.operation_id))
    results={x.operation_id:_sync_one(session,principal,x) for x in ordered}
    if commit:
        session.commit()
    return TeacherOfflineSyncResponse(results=[results[x.operation_id] for x in payload.operations])
