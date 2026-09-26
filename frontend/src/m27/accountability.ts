import { apiFetch } from "../lib/api";

export type QueueItem = {
  case_id: string;
  source_category: string;
  normalized_category: string;
  attention_reasons: string[];
  owner_state: string;
  owner_user_id: string | null;
  review_required: boolean;
  decision_required: boolean;
  open_obligation_id: string | null;
  open_obligation_type: string | null;
  next_required_step: string;
  due_at: string | null;
  sla_status: string;
  compliance_status: string;
  m22_priority: string | null;
  generated_at: string;
  source_freshness: string | null;
  projection_version: number;
  policy_versions: string[];
  provenance_refs: string[];
};

export type QueuePage = { items: QueueItem[]; next_cursor: string | null; generated_at: string };
export type CaseDetail = {
  item: QueueItem;
  source_lineage: Record<string, unknown>[];
  ownership_history: Record<string, unknown>[];
  reviews: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  obligations: Array<Record<string, unknown>>;
  m21_links: Array<Record<string, unknown>>;
  m22_reference: Record<string, unknown> | null;
  generated_at: string;
};
export type MetricResult = {
  metric_id: string;
  metric_version: string;
  status: "COMPUTED" | "NOT_EVALUABLE" | "NOT_COMPUTABLE" | "SUPPRESSED" | "INSUFFICIENT_EVIDENCE";
  value: number | null;
  unit: string;
  numerator: number | null;
  denominator: number | null;
  window_start: string;
  window_end: string;
  freshness: "CURRENT" | "STALE" | "UNKNOWN";
  policy_version: number | null;
  reason: string | null;
  suppression_state: string;
  explanation: { business_question: string; definition: string; numerator_definition: string; denominator_definition: string; exclusions: string[] };
  provenance: { source_read_models: string[]; lineage_digest: string; calculator: string };
};
export type MetricSummary = { items: MetricResult[]; generated_at: string };
export type OutcomeSummary = { status: MetricResult["status"]; observations: Record<string, number>; total_interventions: number; missing_outcome_count: number; reason: string | null; window_start: string; window_end: string };
export type CommandRead = { command: string; id: string; case_id: string | null; created: boolean; decision_type: string | null; lifecycle: string | null; owner_user_id: string | null; review_id: string | null; execution_required: boolean | null; provenance_sha256: string };

const ROOT = "/api/v1/accountability";

export function queueQuery(filters: Record<string, string | boolean | undefined>, cursor?: string) {
  const query = new URLSearchParams();
  Object.entries({ ...filters, cursor }).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && String(value) !== "false") query.set(key, String(value));
  });
  return apiFetch<QueuePage>(`${ROOT}/queue?${query.toString()}`);
}
export function caseDetailQuery(caseId: string) { return apiFetch<CaseDetail>(`${ROOT}/cases/${caseId}/accountability`); }
export function metricsQuery() { return apiFetch<MetricSummary>(`${ROOT}/metrics?window=month`); }
export function outcomesQuery() { return apiFetch<OutcomeSummary>(`${ROOT}/outcomes?window=month`); }

async function commandHash(seed: string): Promise<string> {
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(seed));
    return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  }
  return `${seed.replace(/[^a-f0-9]/gi, "").toLowerCase()}0000000000000000000000000000000000000000000000000000000000000000`.slice(0, 64);
}
export async function commandHashes(command: string, id: string) {
  const requestId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  const idempotency_key = await commandHash(`${command}:idempotency:${id}:${requestId}`);
  const provenance_sha256 = await commandHash(`${command}:provenance:${id}`);
  return { idempotency_key, provenance_sha256 };
}
export function assignOwner(caseId: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/cases/${caseId}/owner/assign`, { method: "POST", body: JSON.stringify(payload) }); }
export function transferOwner(caseId: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/cases/${caseId}/owner/transfer`, { method: "POST", body: JSON.stringify(payload) }); }
export function unassignOwner(caseId: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/cases/${caseId}/owner/unassign`, { method: "POST", body: JSON.stringify(payload) }); }
export function recordReview(caseId: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/cases/${caseId}/review`, { method: "POST", body: JSON.stringify(payload) }); }
export function recordDecision(caseId: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/cases/${caseId}/decision`, { method: "POST", body: JSON.stringify(payload) }); }
export function completeObligation(id: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/obligations/${id}/complete`, { method: "POST", body: JSON.stringify(payload) }); }
export function waiveObligation(id: string, payload: object) { return apiFetch<CommandRead>(`${ROOT}/obligations/${id}/waive`, { method: "POST", body: JSON.stringify(payload) }); }

export const ACCOUNTABILITY_PERMISSIONS = {
  view: "accountability.view",
  review: "accountability.review",
  decide: "accountability.decide",
  ownership: "accountability.ownership.manage",
  complete: "accountability.obligation.complete",
  waive: "accountability.obligation.waive",
};
