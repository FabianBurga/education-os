import { ApiError, apiFetch } from "../lib/api";

export interface AcademicEntity {
  id: string;
  organization_id: string;
  institution_id: string;
  code?: string;
  name?: string;
  status?: string;
  academic_level_id?: string;
  academic_period_id?: string;
  campus_id?: string;
  grade_level_id?: string;
  section_id?: string;
  subject_id?: string;
  course_offering_id?: string;
  staff_profile_id?: string;
  curriculum_subject_id?: string | null;
  starts_on?: string;
  ends_on?: string;
  capacity?: number;
  area?: string | null;
  sort_order?: number;
}

export interface AcademicOptions {
  periods: Array<{ id: string; code: string; name: string; starts_on: string; ends_on: string; status: string }>;
  campuses: Array<{ id: string; name: string }>;
}

export function academicCapabilities(permissions: string[]) {
  const granted = new Set(permissions);
  return { canRead: granted.has("academics.read"), canManage: granted.has("academics.manage"), canAssign: granted.has("academics.assign") };
}

export function academicErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "No tienes el permiso efectivo para esta operación.";
    if (error.status === 404) return "La referencia no existe en la institución activa o no está visible.";
    if (error.status === 409) return "La estructura cambió o una regla de integridad impide el cambio. Recarga e inténtalo de nuevo.";
    if (error.status === 422) return "Revisa los campos y las fechas ingresadas.";
  }
  return "No fue posible completar la solicitud. Inténtalo de nuevo.";
}

export function getAcademicOptions() { return apiFetch<AcademicOptions>("/api/v1/academics/options"); }
export function getAcademicCollection(path: string) { return apiFetch<AcademicEntity[]>(`/api/v1/academics/${path}`); }
export function getPeriods() { return apiFetch<AcademicOptions["periods"]>("/api/v1/academic-periods"); }
export function getAssignmentOptions() { return apiFetch<Array<{ id: string; label: string }>>("/api/v1/academics/assignment-options"); }

export function createAcademicEntity(path: string, payload: Record<string, unknown>) {
  return apiFetch<AcademicEntity>(`/api/v1/academics/${path}`, { method: "POST", body: JSON.stringify(payload) });
}

export function createPeriod(payload: { code: string; name: string; starts_on: string; ends_on: string }) {
  return apiFetch<AcademicEntity>("/api/v1/academic-periods", { method: "POST", body: JSON.stringify(payload) });
}

export function transitionPeriod(id: string, expected_status: string, status: "ACTIVE" | "CLOSED") {
  return apiFetch<AcademicEntity>(`/api/v1/academic-periods/${encodeURIComponent(id)}/status`, {
    method: "PATCH", body: JSON.stringify({ expected_status, status }),
  });
}
