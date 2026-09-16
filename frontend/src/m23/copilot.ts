import { apiFetch } from "../lib/api";

export type CopilotIntent = "INSTITUTION_RISK_SUMMARY" | "STUDENT_SUPPORT_SUMMARY";
export type EvidenceAssessment = "SUFFICIENT" | "LIMITED" | "INSUFFICIENT";
export type ActionProposalStatus = "PROPOSED" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED";
export interface CopilotQueryRequest { intent: CopilotIntent; request_text: string; target_student_profile_id?: string; }
export interface CopilotQueryResponse { run_id: string; status: string; answer: string | null; citations: string[]; evidence_assessment: string | null; failure_code: string | null; }
export interface CopilotRun { run_id: string; intent: CopilotIntent; status: string; failure_code: string | null; answer: string | null; citations: string[]; evidence_assessment: EvidenceAssessment | null; limitations: string[]; provenance: { policy_key: string | null; policy_version: number | null; prompt_key: string | null; prompt_version: number | null; provider_key: string | null; model_key: string | null; model_config_version: number | null; }; created_at: string; completed_at: string | null; }
export interface ActionProposal { id: string; run_id: string; action_type: "CREATE_INTERVENTION"; target_student_profile_id: string; payload: Record<string, unknown>; rationale: string; evidence_citations: string[]; proposed_by_user_id: string; created_at: string; status: ActionProposalStatus; last_event_at: string; decision_by_user_id: string | null; decision_note: string | null; result_ref: Record<string, unknown> | null; failure_code: string | null; }
const ROOT = "/api/v1/copilot";
export function copilotCapabilities(permissions: string[]) { const granted = new Set(permissions); return { canUse: granted.has("copilot.use"), canApprove: granted.has("copilot.action.approve"), canManage: granted.has("copilot.manage") }; }
export function isTeacherAdvisoryOnly(permissions: string[]) { const capabilities = copilotCapabilities(permissions); return capabilities.canUse && !capabilities.canApprove; }
export function queryCopilot(request: CopilotQueryRequest) { return apiFetch<CopilotQueryResponse>(`${ROOT}/queries`, { method: "POST", body: JSON.stringify(request) }); }
export function getCopilotRun(runId: string) { return apiFetch<CopilotRun>(`${ROOT}/runs/${runId}`); }
export function listActionProposals() { return apiFetch<ActionProposal[]>(`${ROOT}/action-proposals`); }
export function approveActionProposal(id: string, note: string) { return apiFetch<ActionProposal>(`${ROOT}/action-proposals/${id}/approve`, { method: "POST", body: JSON.stringify({ note: note.trim() || null }) }); }
export function rejectActionProposal(id: string, reason: string) { return apiFetch<ActionProposal>(`${ROOT}/action-proposals/${id}/reject`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) }); }
