import { apiFetch } from "../lib/api";

export type ContinuitySourceDomain = "M21" | "M27";

export type ContinuityState =
  | "OPEN"
  | "IN_PROGRESS"
  | "MONITORING"
  | "OVERDUE"
  | "PENDING"
  | "ACTIVE"
  | "VOIDED"
  | "SUPERSEDED"
  | string;

export interface TeacherContinuityItem {
  source_domain: ContinuitySourceDomain;
  source_id: string;
  student_profile_id: string | null;
  kind: string;
  source_state: ContinuityState;
  due_at: string | null;
  family_acknowledgement_indicator: boolean;
  linked_at: string | null;
  deep_link: string;
}

export interface TeacherContinuityPage {
  items: TeacherContinuityItem[];
  has_more: boolean;
}

const ROOT = "/api/v1/continuity/worklist";

export function teacherContinuityQuery(
  options: { limit?: number } = {},
): Promise<TeacherContinuityPage> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 25));
  return apiFetch<TeacherContinuityPage>(`${ROOT}?${params.toString()}`);
}
