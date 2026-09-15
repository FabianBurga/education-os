import { apiFetch } from "../lib/api";
import type { StudentIntervention } from "./student-360";

export type InterventionStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "MONITORING"
  | "RESOLVED"
  | "CLOSED"
  | "CANCELLED";

export type ActionStatus =
  | "OPEN"
  | "ACKNOWLEDGED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED"
  | "OVERDUE";

export type OutcomeType =
  | "IMPROVED"
  | "STABLE"
  | "NO_CHANGE"
  | "WORSENED"
  | "REFERRED"
  | "TRANSFERRED"
  | "NOT_ASSESSABLE";

export type FollowUpType =
  | "MEETING"
  | "PHONE_CALL"
  | "FAMILY_CONTACT"
  | "STUDENT_CONVERSATION"
  | "TEACHER_REVIEW"
  | "ACADEMIC_REVIEW"
  | "ATTENDANCE_REVIEW"
  | "PSYCHOLOGY_SESSION"
  | "REFERRAL"
  | "OTHER";

export type Sensitivity =
  | "GENERAL"
  | "RESTRICTED"
  | "CONFIDENTIAL";

export interface InterventionAction {
  id: string;
  intervention_id: string;
  action_type: string;
  title: string;
  description: string | null;
  status: ActionStatus;
  assigned_role_code: string | null;
  assigned_user_id: string | null;
  due_at: string | null;
  acknowledged_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  completed_by_user_id: string | null;
  completion_note: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
  protected_detail: boolean;
}

export interface InterventionActionPage {
  items: InterventionAction[];
  count: number;
}

export interface InterventionFollowUp {
  id: string;
  intervention_id: string;
  followup_type: FollowUpType;
  sensitivity: Sensitivity;
  note: string | null;
  observed_at: string;
  created_by_user_id: string;
  created_at: string;
  protected_detail: boolean;
}

export interface InterventionFollowUpPage {
  items: InterventionFollowUp[];
  count: number;
}

export interface InterventionWorkspaceCapabilities {
  canRead: boolean;
  canUpdate: boolean;
  canAssign: boolean;
  canManageActions: boolean;
  canCreateFollowUp: boolean;
  canResolve: boolean;
  canClose: boolean;
}

export interface InterventionAssignmentInput {
  assigned_role_code?: string | null;
  assigned_user_id?: string | null;
  target_at?: string | null;
}

export interface ActionCreateInput {
  action_type: string;
  title: string;
  description?: string | null;
  assigned_role_code?: string | null;
  assigned_user_id?: string | null;
  due_at?: string | null;
}

export interface FollowUpCreateInput {
  followup_type: FollowUpType;
  sensitivity: Sensitivity;
  note: string;
  observed_at: string;
}

const ROOT = "/api/v1/interventions";

export function interventionWorkspaceCapabilities(
  permissions: string[],
): InterventionWorkspaceCapabilities {
  const granted = new Set(permissions);
  return {
    canRead: granted.has("intervention.read"),
    canUpdate: granted.has("intervention.update"),
    canAssign: granted.has("intervention.assign"),
    canManageActions: granted.has("intervention.action.manage"),
    canCreateFollowUp: granted.has("intervention.followup.create"),
    canResolve: granted.has("intervention.resolve"),
    canClose: granted.has("intervention.close"),
  };
}

export function allowedInterventionTransitions(
  status: InterventionStatus,
): InterventionStatus[] {
  const transitions: Record<
    InterventionStatus,
    InterventionStatus[]
  > = {
    OPEN: ["IN_PROGRESS"],
    IN_PROGRESS: ["MONITORING"],
    MONITORING: ["IN_PROGRESS"],
    RESOLVED: ["IN_PROGRESS", "MONITORING"],
    CLOSED: [],
    CANCELLED: [],
  };
  return transitions[status];
}

export function allowedActionTransitions(
  status: ActionStatus,
): ActionStatus[] {
  const transitions: Record<ActionStatus, ActionStatus[]> = {
    OPEN: ["ACKNOWLEDGED", "IN_PROGRESS", "CANCELLED"],
    ACKNOWLEDGED: ["IN_PROGRESS", "CANCELLED"],
    IN_PROGRESS: ["CANCELLED"],
    COMPLETED: [],
    CANCELLED: [],
    OVERDUE: ["ACKNOWLEDGED", "IN_PROGRESS", "CANCELLED"],
  };
  return transitions[status];
}

export function canCompleteAction(status: ActionStatus): boolean {
  return ["ACKNOWLEDGED", "IN_PROGRESS", "OVERDUE"].includes(
    status,
  );
}

export function minimumFollowUpSensitivity(
  interventionSensitivity: string,
): Sensitivity {
  if (interventionSensitivity === "CONFIDENTIAL") {
    return "CONFIDENTIAL";
  }
  if (interventionSensitivity === "RESTRICTED") {
    return "RESTRICTED";
  }
  return "GENERAL";
}

function withJsonBody(
  method: string,
  body: unknown,
): RequestInit {
  return {
    method,
    body: JSON.stringify(body),
  };
}

export function getIntervention(
  interventionId: string,
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}`,
  );
}

export function listInterventionActions(
  interventionId: string,
): Promise<InterventionActionPage> {
  return apiFetch<InterventionActionPage>(
    `${ROOT}/${encodeURIComponent(interventionId)}/actions?limit=50`,
  );
}

export function listInterventionFollowUps(
  interventionId: string,
): Promise<InterventionFollowUpPage> {
  return apiFetch<InterventionFollowUpPage>(
    `${ROOT}/${encodeURIComponent(interventionId)}/followups?limit=50`,
  );
}

export function assignIntervention(
  interventionId: string,
  payload: InterventionAssignmentInput,
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}/assign`,
    withJsonBody("POST", payload),
  );
}

export function transitionIntervention(
  interventionId: string,
  status: "IN_PROGRESS" | "MONITORING",
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}/transition`,
    withJsonBody("POST", { status }),
  );
}

export function cancelIntervention(
  interventionId: string,
  cancellationReason: string,
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}/cancel`,
    withJsonBody("POST", {
      cancellation_reason: cancellationReason.trim(),
    }),
  );
}

export function resolveIntervention(
  interventionId: string,
  outcomeType: OutcomeType,
  outcomeSummary: string,
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}/resolve`,
    withJsonBody("POST", {
      outcome_type: outcomeType,
      outcome_summary: outcomeSummary.trim(),
    }),
  );
}

export function closeIntervention(
  interventionId: string,
  outcomeType: OutcomeType,
  outcomeSummary: string,
): Promise<StudentIntervention> {
  return apiFetch<StudentIntervention>(
    `${ROOT}/${encodeURIComponent(interventionId)}/close`,
    withJsonBody("POST", {
      outcome_type: outcomeType,
      outcome_summary: outcomeSummary.trim(),
    }),
  );
}

export function createInterventionAction(
  interventionId: string,
  payload: ActionCreateInput,
): Promise<InterventionAction> {
  return apiFetch<InterventionAction>(
    `${ROOT}/${encodeURIComponent(interventionId)}/actions`,
    withJsonBody("POST", payload),
  );
}

export function transitionInterventionAction(
  actionId: string,
  status: "ACKNOWLEDGED" | "IN_PROGRESS" | "CANCELLED",
): Promise<InterventionAction> {
  return apiFetch<InterventionAction>(
    `${ROOT}/actions/${encodeURIComponent(actionId)}/transition`,
    withJsonBody("POST", { status }),
  );
}

export function completeInterventionAction(
  actionId: string,
  completionNote: string,
): Promise<InterventionAction> {
  return apiFetch<InterventionAction>(
    `${ROOT}/actions/${encodeURIComponent(actionId)}/complete`,
    withJsonBody("POST", {
      completion_note: completionNote.trim() || null,
    }),
  );
}

export function createInterventionFollowUp(
  interventionId: string,
  payload: FollowUpCreateInput,
): Promise<InterventionFollowUp> {
  return apiFetch<InterventionFollowUp>(
    `${ROOT}/${encodeURIComponent(interventionId)}/followups`,
    withJsonBody("POST", payload),
  );
}
