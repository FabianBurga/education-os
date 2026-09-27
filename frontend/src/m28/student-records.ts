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

export interface StudentPlacement {
  id: string;
  student_profile_id: string;
  academic_period_id: string;
  enrollment_id: string;
  section_id: string;
  status: "ACTIVE" | "TRANSFERRED" | "WITHDRAWN";
  assigned_on: string;
  ended_on: string | null;
  section_code: string;
  section_name: string;
  is_current: boolean;
}

export interface PlacementOptions {
  sections: Array<{ id: string; code: string; name: string }>;
  current_placement_id: string | null;
  current_section_id: string | null;
}

export interface PlacementCommandResult {
  id: string;
  academic_period_id: string;
  enrollment_id: string;
  section_id: string;
  status: "ACTIVE" | "TRANSFERRED" | "WITHDRAWN";
  assigned_on: string;
  ended_on: string | null;
}

export function enrollmentCapabilities(permissions: string[]) {
  const granted = new Set(permissions);
  return { canRead: granted.has("enrollments.read"), canManage: granted.has("enrollments.manage") };
}

export function placementCapabilities(permissions: string[]) {
  const granted = new Set(permissions);
  return {
    canRead: granted.has("academics.read") && granted.has("students.read") && granted.has("enrollments.read"),
    canAssign: granted.has("academics.assign"),
  };
}

export function placementErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "No tienes permiso efectivo para consultar o cambiar esta ubicación.";
    if (error.status === 404) return "La matrícula o sección no está disponible en la institución activa.";
    if (error.status === 409) return "La ubicación cambió o la evidencia existente impide el traslado. Actualiza el estado antes de continuar.";
    if (error.status === 422) return "La fecha o selección no cumple las condiciones de ubicación.";
  }
  return "No fue posible completar la operación de ubicación. Inténtalo de nuevo.";
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

export function getStudentPlacements(studentId: string) {
  return apiFetch<StudentPlacement[]>(`/api/v1/academics/students/${encodeURIComponent(studentId)}/placements`);
}

export function getPlacementOptions(enrollmentId: string) {
  return apiFetch<PlacementOptions>(`/api/v1/academics/enrollments/${encodeURIComponent(enrollmentId)}/placement-options`);
}

export function assignStudentSection(input: { enrollment_id: string; section_id: string; assigned_on: string }) {
  return apiFetch<PlacementCommandResult>("/api/v1/academics/student-section-assignments", {
    method: "POST", body: JSON.stringify(input),
  });
}

export function transferStudentSection(enrollmentId: string, input: {
  expected_current_placement_id: string; section_id: string; effective_on: string;
}) {
  return apiFetch<PlacementCommandResult>(`/api/v1/academics/enrollments/${encodeURIComponent(enrollmentId)}/placements/transfer`, {
    method: "POST", body: JSON.stringify(input),
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
