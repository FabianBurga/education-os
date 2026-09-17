import { ApiError, apiFetch } from "../lib/api";

const ROOT = "/api/v1/integrations";

export interface IntegrationConnector {
  id: string;
  connector_key: string;
  connector_type: "FILE_CSV" | "CSV_STUDENT_ENROLLMENT";
  display_name: string;
  status: "ENABLED" | "DISABLED";
  config_version: number;
  configuration: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface IntegrationRun {
  id: string;
  connector_id: string;
  connector_key: string;
  connector_display_name: string;
  mapping_id: string | null;
  initiated_by_user_id: string;
  source_kind: string;
  mode: string;
  source_filename: string | null;
  source_fingerprint_sha256: string;
  connector_config_version: number;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  conflict_rows: number;
  applied_rows: number;
  failed_rows: number;
  created_at: string;
}

export interface IntegrationRunItem {
  id: string;
  source_row_number: number | null;
  external_student_id: string | null;
  canonical_entity_type: string;
  operation_class: string;
  status: string;
  error_code: string | null;
  academic_period_code: string | null;
  campus_id: string | null;
  student_code: string | null;
  idempotency_key: string | null;
  student_profile_id: string | null;
  enrollment_id: string | null;
  created_at: string;
}

export interface IntegrationRunEvent {
  sequence: number;
  event_type: string;
  run_item_id: string | null;
  actor_user_id: string | null;
  created_at: string;
  metadata: {
    workflow: string | null;
    source_filename: string | null;
    source_sha256: string | null;
    total_rows: number | null;
    valid_rows: number | null;
    invalid_rows: number | null;
    conflict_rows: number | null;
    dry_run: boolean | null;
    external_student_id: string | null;
    student_profile_id: string | null;
    enrollment_id: string | null;
    error_code: string | null;
    applied_at: string | null;
  };
}

export interface CsvPreview {
  run: IntegrationRun;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  conflict_rows: number;
}

export interface IntegrationCapabilities {
  canView: boolean;
  canManage: boolean;
  canRun: boolean;
  canAudit: boolean;
}

export const CSV_IMPORT_CONTRACT = {
  required: ["external_student_id", "given_names", "family_names", "academic_period_code", "campus_id"],
  optional: ["student_code", "enrollment_number", "enrollment_status", "enrolled_on"],
  limits: ["UTF-8", "Máximo 1 MB", "Máximo 1.000 filas", "Máximo 9 columnas", "Máximo 320 caracteres por celda"],
} as const;

export function integrationCapabilities(permissions: string[]): IntegrationCapabilities {
  const granted = new Set(permissions);
  return {
    canView: granted.has("integrations.view"),
    canManage: granted.has("integrations.manage"),
    canRun: granted.has("integrations.run"),
    canAudit: granted.has("integrations.audit.read"),
  };
}

export function csvFileIsAccepted(file: File): boolean {
  return file.name.toLowerCase().endsWith(".csv") && file.size <= 1_000_000;
}

export function canApplyPreview(canRun: boolean, previewRunId: string | null, selectedRunId: string | null, status: string | undefined): boolean {
  return canRun && previewRunId === selectedRunId && status === "VALIDATED";
}

export function canReadAuditEvents(canAudit: boolean, runId: string | null): boolean {
  return canAudit && Boolean(runId);
}

export function integrationErrorMessage(error: unknown): string {
  const message = error instanceof ApiError ? error.message : "";
  if (message.includes("ACADEMIC_PERIOD_NOT_FOUND")) return "No se encontró el período académico indicado.";
  if (message.includes("EXTERNAL_ID_DUPLICATE")) return "El identificador externo entra en conflicto con una referencia existente.";
  if (message.includes("ALREADY_APPLIED")) return "La fila ya fue aplicada anteriormente.";
  if (message.includes("CSV_ROW_INVALID")) return "La fila no cumple el contrato CSV requerido.";
  if (message.includes("CSV_SCHEMA_INVALID")) return "El archivo no cumple el esquema CSV requerido.";
  if (message.includes("CSV_TOO_LARGE")) return "El archivo supera el límite permitido de 1 MB.";
  if (error instanceof ApiError && error.status === 403) return "No tienes permiso para realizar esta operación.";
  if (error instanceof ApiError && error.status === 404) return "El recurso solicitado no está disponible en tu contexto.";
  return "No se pudo completar la operación. Verifica el archivo o inténtalo nuevamente.";
}

export function itemErrorMessage(code: string | null): string | null {
  return code ? `${integrationErrorMessage(new ApiError(422, code))} Código: ${code}` : null;
}

export function listConnectors() { return apiFetch<IntegrationConnector[]>(`${ROOT}/connectors`); }
export function createConnector(payload: Pick<IntegrationConnector, "connector_key" | "connector_type" | "display_name"> & { configuration?: Record<string, unknown> }) {
  return apiFetch<IntegrationConnector>(`${ROOT}/connectors`, { method: "POST", body: JSON.stringify(payload) });
}
export function setConnectorStatus(connectorId: string, enabled: boolean) {
  return apiFetch<IntegrationConnector>(`${ROOT}/connectors/${connectorId}/${enabled ? "enable" : "disable"}`, { method: "POST" });
}
export function previewStudentEnrollmentCsv(connectorId: string, file: File) {
  return apiFetch<CsvPreview>(`${ROOT}/connectors/${connectorId}/csv/student-enrollment/preview`, {
    method: "POST", headers: { "Content-Type": "text/csv", "X-Source-Filename": file.name }, body: file,
  });
}
export function listRuns() { return apiFetch<IntegrationRun[]>(`${ROOT}/runs?limit=100`); }
export function getRun(runId: string) { return apiFetch<IntegrationRun>(`${ROOT}/runs/${runId}`); }
export function listRunItems(runId: string) { return apiFetch<IntegrationRunItem[]>(`${ROOT}/runs/${runId}/items`); }
export function listRunEvents(runId: string) { return apiFetch<IntegrationRunEvent[]>(`${ROOT}/runs/${runId}/events`); }
export function applyRun(runId: string) { return apiFetch<IntegrationRun>(`${ROOT}/runs/${runId}/apply`, { method: "POST" }); }
