import { ApiError, apiFetch } from "../lib/api";

export interface StudentRecord {
  id: string;
  display_name: string;
  student_code: string | null;
  status: "ACTIVE" | "INACTIVE" | "ARCHIVED";
  updated_at: string;
}

export interface StudentRecordPage {
  items: StudentRecord[];
  next_cursor: string | null;
}

export interface EnrollmentRecord {
  id: string;
  student_profile_id: string;
  academic_period_id: string;
  academic_period_code: string;
  academic_period_name: string;
  campus_id: string;
  enrollment_number: string | null;
  status: "PENDING" | "ACTIVE" | "WITHDRAWN" | "COMPLETED" | "CANCELLED";
  enrolled_on: string | null;
  withdrawn_on: string | null;
  updated_at: string;
  allowed_actions: string[];
}

export interface EnrollmentHistoryEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  created_at: string;
  details: Record<string, unknown>;
}

export interface EnrollmentOptions {
  periods: Array<{ id: string; code: string; name: string; starts_on: string; ends_on: string; status: string }>;
  campuses: Array<{ id: string; name: string }>;
}

export function enrollmentCapabilities(permissions: string[]) {
  const granted = new Set(permissions);
  return { canRead: granted.has("enrollments.read"), canManage: granted.has("enrollments.manage") };
}

export function studentRecordCapabilities(permissions: string[]) {
  const granted = new Set(permissions);
  return {
    canRead: granted.has("students.read"),
    canManage: granted.has("students.manage"),
  };
}

export function studentRecordErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "No tienes permiso para esta operación.";
    if (error.status === 404) return "El registro no está disponible en tu institución o alcance.";
    if (error.status === 409) return "El registro cambió o tiene una matrícula activa. Recarga antes de continuar.";
    if (error.status === 422) return "Revisa los campos e inténtalo de nuevo.";
  }
  return "No fue posible completar la solicitud. Inténtalo de nuevo.";
}

export function getStudentRecords(cursor: string | null): Promise<StudentRecordPage> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  return apiFetch<StudentRecordPage>(`/api/v1/students/records?${query.toString()}`);
}

export function getStudentRecord(id: string): Promise<StudentRecord> {
  return apiFetch<StudentRecord>(`/api/v1/students/${encodeURIComponent(id)}`);
}

export function getStudentEnrollments(studentId: string): Promise<EnrollmentRecord[]> {
  return apiFetch<EnrollmentRecord[]>(`/api/v1/enrollments?student_profile_id=${encodeURIComponent(studentId)}&limit=100`);
}

export function getEnrollmentOptions(): Promise<EnrollmentOptions> {
  return apiFetch<EnrollmentOptions>("/api/v1/enrollments/options");
}

export function createEnrollment(input: {
  student_profile_id: string;
  academic_period_id: string;
  campus_id: string;
  enrollment_number: string | null;
  status: "PENDING" | "ACTIVE";
  enrolled_on: string | null;
}): Promise<EnrollmentRecord> {
  return apiFetch<EnrollmentRecord>("/api/v1/enrollments", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getEnrollmentHistory(enrollmentId: string): Promise<EnrollmentHistoryEntry[]> {
  return apiFetch<EnrollmentHistoryEntry[]>(`/api/v1/enrollments/${encodeURIComponent(enrollmentId)}/history`);
}

export function transitionEnrollment(
  enrollmentId: string,
  input: { status: string; expected_updated_at: string; effective_on: string | null; reason_code: string | null },
): Promise<EnrollmentRecord> {
  return apiFetch<EnrollmentRecord>(`/api/v1/enrollments/${encodeURIComponent(enrollmentId)}/status`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function updateStudentRecord(
  id: string,
  input: Pick<StudentRecord, "student_code" | "status"> & { expected_updated_at: string },
): Promise<StudentRecord> {
  return apiFetch<StudentRecord>(`/api/v1/students/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}
