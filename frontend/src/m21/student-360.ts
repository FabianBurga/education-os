import { apiFetch } from "../lib/api";

export type TimelineCategory =
  | "ENROLLMENT"
  | "ATTENDANCE"
  | "ACADEMIC"
  | "SIGNAL"
  | "INTERVENTION"
  | "ACTION"
  | "FOLLOW_UP"
  | "COMMUNICATION"
  | "OUTCOME"
  | "SYSTEM";

export type TimelineSensitivity =
  | "GENERAL"
  | "RESTRICTED"
  | "CONFIDENTIAL";

export interface StudentTimelineEntry {
  id: string;
  student_profile_id: string;
  ledger_event_id: string;
  ledger_position: number;
  event_type: string;
  event_version: number;
  category: TimelineCategory;
  importance: string;
  sensitivity: TimelineSensitivity;
  title: string;
  summary: string | null;
  source_aggregate_type: string;
  source_aggregate_id: string;
  actor_user_id: string | null;
  correlation_id: string | null;
  causation_id: string | null;
  context_json: Record<string, unknown>;
  occurred_at: string;
  recorded_at: string;
  projected_at: string;
}

export interface StudentTimelinePage {
  student_profile_id: string;
  entries: StudentTimelineEntry[];
  next_before_position: number | null;
}

export interface StudentIntervention {
  id: string;
  student_profile_id: string;
  intervention_type: string;
  severity: string;
  status: string;
  sensitivity: string;
  title: string;
  reason: string | null;
  objective: string | null;
  origin_type: string;
  assigned_role_code: string | null;
  assigned_user_id: string | null;
  opened_at: string;
  target_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  outcome_type: string | null;
  outcome_summary: string | null;
  protected_detail: boolean;
}

export interface StudentInterventionPage {
  items: StudentIntervention[];
  count: number;
}

export interface TimelineFilters {
  category?: TimelineCategory | "";
  sensitivity?: TimelineSensitivity | "";
  beforePosition?: number;
}

export interface Student360Capabilities {
  canReadTimeline: boolean;
  canReadInterventions: boolean;
  canReadSuggestions: boolean;
}

export function student360Capabilities(
  permissions: string[],
): Student360Capabilities {
  const granted = new Set(permissions);
  return {
    canReadTimeline: granted.has("student_timeline.read"),
    canReadInterventions: granted.has("intervention.read"),
    canReadSuggestions: granted.has(
      "intervention.suggestion.read",
    ),
  };
}

export function buildStudentTimelinePath(
  studentProfileId: string,
  filters: TimelineFilters = {},
): string {
  const params = new URLSearchParams();
  params.set("limit", "50");

  if (filters.beforePosition !== undefined) {
    params.set(
      "before_position",
      String(filters.beforePosition),
    );
  }
  if (filters.category) {
    params.set("category", filters.category);
  }
  if (filters.sensitivity) {
    params.set("sensitivity", filters.sensitivity);
  }

  return (
    `/api/v1/student-timeline/students/` +
    `${encodeURIComponent(studentProfileId)}?${params.toString()}`
  );
}

export function buildStudentInterventionsPath(
  studentProfileId: string,
): string {
  const params = new URLSearchParams();
  params.set("limit", "50");
  return (
    `/api/v1/interventions/students/` +
    `${encodeURIComponent(studentProfileId)}?${params.toString()}`
  );
}

export function getStudentTimeline(
  studentProfileId: string,
  filters: TimelineFilters = {},
): Promise<StudentTimelinePage> {
  return apiFetch<StudentTimelinePage>(
    buildStudentTimelinePath(studentProfileId, filters),
  );
}

export function getStudentInterventions(
  studentProfileId: string,
): Promise<StudentInterventionPage> {
  return apiFetch<StudentInterventionPage>(
    buildStudentInterventionsPath(studentProfileId),
  );
}

export function timelineCategoryTone(
  category: TimelineCategory,
): "neutral" | "success" | "warning" | "danger" {
  if (category === "OUTCOME") {
    return "success";
  }
  if (category === "SIGNAL") {
    return "warning";
  }
  if (category === "INTERVENTION") {
    return "danger";
  }
  return "neutral";
}

export function timelineSensitivityTone(
  sensitivity: TimelineSensitivity,
): "neutral" | "success" | "warning" | "danger" {
  if (sensitivity === "CONFIDENTIAL") {
    return "danger";
  }
  if (sensitivity === "RESTRICTED") {
    return "warning";
  }
  return "neutral";
}
