import { queryOptions } from "@tanstack/react-query";
import { ApiError, apiFetch } from "../lib/api";
import type { UiBootstrap } from "../types/bootstrap";

export const MENTOR_FOCUSES = ["OVERVIEW", "PRIORITIES", "FOLLOW_UPS"] as const;
export type BriefingFocus = typeof MENTOR_FOCUSES[number];
export const FOCUS_LABELS: Record<BriefingFocus, string> = {
  OVERVIEW: "Panorama", PRIORITIES: "Prioridades", FOLLOW_UPS: "Revisión humana",
};

// agents.view belongs to the inherited run-read API, not the M26 capability policy.
export const MENTOR_UI_PERMISSIONS = ["agents.use", "intelligence.read", "agents.view"];
export function canUseMentor(permissions: string[]) {
  return MENTOR_UI_PERMISSIONS.every(permission => permissions.includes(permission));
}

export interface MentorBriefing {
  briefing_focus: BriefingFocus;
  summary: string;
  key_findings: { text: string; evidence_refs: string[] }[];
  caveats: string[];
  evidence_refs: string[];
  explanation_mode: "DETERMINISTIC_FALLBACK" | "FAKE_PROVIDER";
  snapshot_date: string;
  freshness: string;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid briefing");
  return value as Record<string, unknown>;
}
function boundedText(value: unknown, maximum: number): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) throw new Error("Invalid briefing");
  return value;
}
function boundedList(value: unknown, maximum: number): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) throw new Error("Invalid briefing");
  return value;
}

// Keep only presentation fields in the query cache. No control-plane payload spreading.
export function projectMentorBriefing(value: unknown, focus: BriefingFocus): MentorBriefing {
  const run = record(value);
  const output = record(run.output);
  if (run.status !== "COMPLETED" || run.agent_key !== "mentor_institution_briefing" ||
      output.agent_key !== run.agent_key || output.briefing_focus !== focus ||
      !["DETERMINISTIC_FALLBACK", "FAKE_PROVIDER"].includes(String(output.explanation_mode))) {
    throw new Error("Invalid briefing");
  }
  const snapshot_date = boundedText(output.snapshot_date, 10);
  const freshness = boundedText(output.freshness, 40);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(snapshot_date) ||
      !Number.isFinite(Date.parse(`${snapshot_date}T00:00:00Z`)) ||
      !/^(CURRENT|STALE_\d+_DAYS)$/.test(freshness)) throw new Error("Invalid briefing");
  // The frozen Mentor pack has one aggregate source, cited as ev_01.
  const sources = boundedList(output.evidence_refs, 1);
  if (sources.length !== 1 || record(sources[0]).source_module !== "intelligence" ||
      record(sources[0]).source_entity_type !== "InstitutionIntelligenceDaily") throw new Error("Invalid briefing");
  const key_findings = boundedList(output.key_findings, 8).map(value => {
    const finding = record(value);
    const refs = boundedList(finding.evidence_refs, 1);
    if (refs.length !== 1 || refs[0] !== "ev_01") throw new Error("Invalid briefing");
    return { text: boundedText(finding.text, 700), evidence_refs: ["ev_01"] };
  });
  if (!key_findings.length) throw new Error("Invalid briefing");
  return {
    briefing_focus: focus, summary: boundedText(output.summary, 1200), key_findings,
    caveats: boundedList(output.caveats, 8).map(value => boundedText(value, 1200)),
    evidence_refs: ["ev_01"], explanation_mode: output.explanation_mode as MentorBriefing["explanation_mode"],
    snapshot_date, freshness,
  };
}

export function mentorQueryOptions(bootstrap: UiBootstrap, focus: BriefingFocus) {
  return queryOptions({
    queryKey: ["m26-mentor", bootstrap.tenant.organization_id, bootstrap.tenant.institution_id,
      bootstrap.user.user_id, [...bootstrap.permissions].sort().join(","), focus],
    queryFn: async ({ signal }) => projectMentorBriefing(await apiFetch<unknown>(
      "/api/v1/agents/mentor_institution_briefing/runs",
      { method: "POST", body: JSON.stringify({ briefing_focus: focus }), signal },
    ), focus),
    enabled: canUseMentor(bootstrap.permissions), retry: false,
    staleTime: 0, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
}

export function mentorErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Tu sesión ha vencido. Vuelve a iniciar sesión para consultar el resumen.";
    if (error.status === 403) return "El resumen no está disponible con tus permisos actuales.";
    if (error.status === 404) return "No hay evidencia institucional disponible para tu contexto. No se ha generado un resumen.";
  }
  return "No fue posible cargar un resumen verificado. Inténtalo de nuevo más tarde.";
}

export function freshnessLabel(freshness: string) {
  return freshness === "CURRENT" ? "Información vigente" : "Información desactualizada";
}
