import type { UiBootstrap } from "./types/bootstrap";
import type { TeacherOfflineAttendanceBase, TeacherOfflineAttendanceRow, TeacherOfflineQueuedOperation } from "./types/teacher-offline";

export function teacherOfflinePartitionKey(bootstrap: UiBootstrap): string { return [bootstrap.tenant.organization_id,bootstrap.tenant.institution_id,bootstrap.user.user_id].join(":"); }
export function teacherOfflineTargetKey(classSessionId:string,assignmentId:string):string { return `${classSessionId}:${assignmentId}`; }
export function teacherOfflineQueueKey(partitionKey:string,classSessionId:string,assignmentId:string):string { return `${partitionKey}:${teacherOfflineTargetKey(classSessionId,assignmentId)}`; }
export function chunkTeacherOfflineOperations<T>(items:T[],size=100):T[][] { if(!Number.isInteger(size)||size<1||size>100)throw new Error("Teacher offline batch size must be between 1 and 100"); const batches:T[][]=[]; for(let offset=0;offset<items.length;offset+=size)batches.push(items.slice(offset,offset+size)); return batches; }
export function teacherOfflineSnapshotExpired(expiresAt:string,now=Date.now()):boolean { const expires=Date.parse(expiresAt); return Number.isNaN(expires)||expires<=now; }
export function attendanceBaseFromRow(row:TeacherOfflineAttendanceRow):TeacherOfflineAttendanceBase { return {attendance_record_id:row.attendance_record_id,attendance_code_id:row.attendance_code_id,minutes_late:row.minutes_late,note:row.note}; }
export function effectiveAttendanceRow(row:TeacherOfflineAttendanceRow,queued:TeacherOfflineQueuedOperation|undefined):TeacherOfflineAttendanceRow { if(!queued)return row; return {...row,attendance_code_id:queued.operation.desired.attendance_code_id,minutes_late:queued.operation.desired.minutes_late,note:queued.operation.desired.note}; }
