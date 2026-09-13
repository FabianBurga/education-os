export interface TeacherOfflineAttendanceCode { id:string; code:string; label:string; semantic:string; counts_as_present:boolean; counts_as_absent:boolean; counts_as_late:boolean; }
export interface TeacherOfflineClassRead { course_offering_id:string; academic_period_id:string; academic_period_name:string; section_id:string; section_name:string; grade_name:string; subject_id:string; subject_code:string; subject_name:string; assignment_role:string; student_count:number; }
export interface TeacherOfflineRosterStudent { student_section_assignment_id:string; student_profile_id:string; student_code:string|null; student_name:string; enrollment_number:string|null; }
export interface TeacherOfflineClassSession { id:string; course_offering_id:string; section_id:string; session_date:string; starts_at:string; ends_at:string; status:string; }
export interface TeacherOfflineAttendanceRow { student_section_assignment_id:string; student_profile_id:string; student_code:string|null; student_name:string; attendance_record_id:string|null; attendance_code_id:string|null; attendance_code:string|null; attendance_label:string|null; minutes_late:number; note:string|null; }
export interface TeacherOfflineSessionSnapshot { session:TeacherOfflineClassSession; attendance:TeacherOfflineAttendanceRow[]; }
export interface TeacherOfflineClassSnapshot { classroom:TeacherOfflineClassRead; roster:TeacherOfflineRosterStudent[]; sessions:TeacherOfflineSessionSnapshot[]; }
export interface TeacherOfflineSnapshot { snapshot_version:number; generated_at:string; expires_at:string; days:number; classes:TeacherOfflineClassSnapshot[]; attendance_codes:TeacherOfflineAttendanceCode[]; }
export interface TeacherOfflineAttendanceBase { attendance_record_id:string|null; attendance_code_id:string|null; minutes_late:number; note:string|null; }
export interface TeacherOfflineAttendanceDesired { student_section_assignment_id:string; attendance_code_id:string; minutes_late:number; note:string|null; }
export interface TeacherOfflineAttendanceOperation { operation_id:string; operation_type:"ATTENDANCE_MARK"; class_session_id:string; base:TeacherOfflineAttendanceBase; desired:TeacherOfflineAttendanceDesired; }
export type TeacherOfflineSyncStatus="APPLIED"|"REPLAYED"|"CONFLICT"|"IDEMPOTENCY_MISMATCH"|"REJECTED";
export interface TeacherOfflineSyncResult { operation_id:string; status:TeacherOfflineSyncStatus; result_entity_id:string|null; server_state:TeacherOfflineAttendanceBase|null; detail:string|null; }
export interface TeacherOfflineSyncResponse { results:TeacherOfflineSyncResult[]; }
export type TeacherOfflineQueueStatus="PENDING"|"CONFLICT";
export interface TeacherOfflineQueuedOperation { queueKey:string; partitionKey:string; operationId:string; targetKey:string; createdAt:string; status:TeacherOfflineQueueStatus; detail:string|null; serverState:TeacherOfflineAttendanceBase|null; operation:TeacherOfflineAttendanceOperation; }
