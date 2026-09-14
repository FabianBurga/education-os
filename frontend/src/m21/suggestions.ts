import { apiFetch } from "../lib/api";

export type SuggestionStatus =
  | "PENDING"
  | "ACCEPTED"
  | "DISMISSED"
  | "EXPIRED";

export type SuggestionSeverity =
  | "LOW"
  | "MEDIUM"
  | "HIGH"
  | "CRITICAL";

export type SuggestionSensitivity =
  | "GENERAL"
  | "RESTRICTED"
  | "CONFIDENTIAL";

export interface InterventionSuggestionEvidence {
  id: string;
  suggestion_id: string;
  evidence_type: string;
  evidence_id: string;
  created_at: string;
}

export interface InterventionSuggestion {
  id: string;
  organization_id: string;
  institution_id: string;
  student_profile_id: string;
  academic_period_id: string | null;
  section_id: string | null;
  rule_key: string;
  rule_version: number;
  generation_mode: string;
  dedupe_key: string;
  recommended_intervention_type: string;
  severity: SuggestionSeverity;
  sensitivity: SuggestionSensitivity;
  title: string;
  rationale_summary: string;
  status: SuggestionStatus;
  generated_at: string;
  last_seen_at: string;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  review_note: string | null;
  accepted_intervention_id: string | null;
  created_at: string;
  updated_at: string;
  evidence: InterventionSuggestionEvidence[];
}

export interface InterventionSuggestionPage {
  items: InterventionSuggestion[];
  count: number;
}

export interface SuggestionRefreshResult {
  generated: number;
  refreshed: number;
  expired: number;
  pending: number;
}

export interface SuggestionFilters {
  status?: SuggestionStatus | "";
  severity?: SuggestionSeverity | "";
  sensitivity?: SuggestionSensitivity | "";
  studentProfileId?: string;
}

export interface SuggestionCapabilities {
  canRead: boolean;
  canGenerate: boolean;
  canReview: boolean;
}

export type SuggestionReviewAction = "accept" | "dismiss";

const API_ROOT = "/api/v1/interventions/suggestions";

export function suggestionCapabilities(
  permissions: string[],
): SuggestionCapabilities {
  const granted = new Set(permissions);
  return {
    canRead: granted.has("intervention.suggestion.read"),
    canGenerate: granted.has("intervention.suggestion.generate"),
    canReview: granted.has("intervention.suggestion.review"),
  };
}

export function buildSuggestionListPath(
  filters: SuggestionFilters,
): string {
  const params = new URLSearchParams();
  params.set("limit", "50");

  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.severity) {
    params.set("severity", filters.severity);
  }
  if (filters.sensitivity) {
    params.set("sensitivity", filters.sensitivity);
  }
  if (filters.studentProfileId?.trim()) {
    params.set(
      "student_profile_id",
      filters.studentProfileId.trim(),
    );
  }

  return `${API_ROOT}?${params.toString()}`;
}

export function reviewNoteError(note: string): string | null {
  const normalized = note.trim();
  if (!normalized) {
    return "Escribe una nota de revisión antes de continuar.";
  }
  if (normalized.length > 1000) {
    return "La nota de revisión no puede superar 1000 caracteres.";
  }
  return null;
}

export function isSuggestionReviewable(
  status: SuggestionStatus,
): boolean {
  return status === "PENDING";
}

export function suggestionSeverityTone(
  severity: SuggestionSeverity,
): "neutral" | "success" | "warning" | "danger" {
  if (severity === "CRITICAL") {
    return "danger";
  }
  if (severity === "HIGH") {
    return "warning";
  }
  if (severity === "LOW") {
    return "success";
  }
  return "neutral";
}

export function suggestionStatusTone(
  status: SuggestionStatus,
): "neutral" | "success" | "warning" | "danger" {
  if (status === "ACCEPTED") {
    return "success";
  }
  if (status === "DISMISSED" || status === "EXPIRED") {
    return "neutral";
  }
  return "warning";
}

export function suggestionSensitivityTone(
  sensitivity: SuggestionSensitivity,
): "neutral" | "success" | "warning" | "danger" {
  if (sensitivity === "CONFIDENTIAL") {
    return "danger";
  }
  if (sensitivity === "RESTRICTED") {
    return "warning";
  }
  return "neutral";
}

export function listSuggestions(
  filters: SuggestionFilters,
): Promise<InterventionSuggestionPage> {
  return apiFetch<InterventionSuggestionPage>(
    buildSuggestionListPath(filters),
  );
}

export function refreshSuggestions(): Promise<SuggestionRefreshResult> {
  return apiFetch<SuggestionRefreshResult>(
    `${API_ROOT}/refresh`,
    { method: "POST" },
  );
}

export function reviewSuggestion(
  suggestionId: string,
  action: SuggestionReviewAction,
  reviewNote: string,
): Promise<InterventionSuggestion> {
  return apiFetch<InterventionSuggestion>(
    `${API_ROOT}/${suggestionId}/${action}`,
    {
      method: "POST",
      body: JSON.stringify({ review_note: reviewNote.trim() }),
    },
  );
}
