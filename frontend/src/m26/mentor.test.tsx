import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { modulesForContext } from "../navigation";
import { MentorBriefingView, type MentorViewProps } from "../pages/mentor-briefing-page";
import type { UiBootstrap } from "../types/bootstrap";
import { canUseMentor, MENTOR_FOCUSES, MENTOR_UI_PERMISSIONS, mentorErrorMessage, mentorQueryOptions, projectMentorBriefing, type BriefingFocus } from "./mentor";

const context: UiBootstrap = {
  user: { user_id: "actor", display_name: "Test Rector", login_email: "test@example.invalid" },
  tenant: { organization_id: "org", institution_id: "institution", organization_name: "Test", institution_name: "Test", institution_type: "PRIVATE" },
  roles: ["ACADEMIC_COORDINATOR"], permissions: MENTOR_UI_PERMISSIONS,
  capabilities: {}, profiles: { staff: true, student: false, guardian: false },
};
function run(focus: BriefingFocus = "OVERVIEW", changes = {}) {
  return {
    agent_key: "mentor_institution_briefing", status: "COMPLETED",
    output: {
      agent_key: "mentor_institution_briefing", briefing_focus: focus,
      summary: "La institución registra 3 señales abiertas: 1 de prioridad alta, 1 media y 1 baja.",
      key_findings: [{ text: "Revise las categorías actuales.", evidence_refs: ["ev_01"] }],
      caveats: ["All decisions remain with authorized humans."], snapshot_date: "2026-09-19", freshness: "CURRENT",
      explanation_mode: "DETERMINISTIC_FALLBACK",
      evidence_refs: [{ source_module: "intelligence", source_entity_type: "InstitutionIntelligenceDaily", source_entity_id: "hidden-id", provenance_sha256: "hidden-hash" }],
      snapshot_id: "hidden-id", provider_failure_code: "hidden-error", evidence_manifest_sha256: "hidden-hash",
      provider_name: "hidden-provider", model_name: "hidden-model", raw_prompt: "hidden-prompt", raw_response: "hidden-response",
      ...changes,
    },
  };
}
function render(props: Partial<MentorViewProps> = {}) {
  return renderToStaticMarkup(createElement(MentorBriefingView, {
    focus: "OVERVIEW", onFocus: vi.fn(), onRefresh: vi.fn(), loading: false, allowed: true,
    briefing: projectMentorBriefing(run(), "OVERVIEW"), ...props,
  }));
}
afterEach(() => vi.unstubAllGlobals());

describe("Mentor presentation contract", () => {
  it("uses effective permissions without a Rector role check", () => {
    expect(canUseMentor(context.permissions)).toBe(true);
    expect(modulesForContext(context).map(m => m.id)).toContain("mentor");
    for (const permission of MENTOR_UI_PERMISSIONS) {
      const permissions = context.permissions.filter(p => p !== permission);
      expect(canUseMentor(permissions)).toBe(false);
      expect(modulesForContext({ ...context, permissions }).map(m => m.id)).not.toContain("mentor");
    }
  });
  it.each(MENTOR_FOCUSES)("renders %s and marks exactly one native focus button pressed", focus => {
    const html = render({ focus, briefing: projectMentorBriefing(run(focus), focus) });
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain("Enfoque del resumen");
    expect(html).toContain("Información vigente");
    expect(html).toMatch(/<time datetime="2026-09-19"/i);
    expect(html).toContain("Resumen generado a partir de datos institucionales disponibles");
    expect(html).not.toMatch(/textarea|<input|DETERMINISTIC_FALLBACK|FAKE_PROVIDER/);
  });
  it("shows stale evidence with its backend date and caveat, without a frontend clock", () => {
    const html = render({ briefing: projectMentorBriefing(run("OVERVIEW", { freshness: "STALE_4_DAYS" }), "OVERVIEW") });
    expect(html).toContain("Información desactualizada");
    expect(html).toContain("Revisa su fecha");
    expect(html).toContain("2026-09-19");
  });
  it("labels assisted explanations without showing provider or model metadata", () => {
    const html = render({ briefing: projectMentorBriefing(run("OVERVIEW", { explanation_mode: "FAKE_PROVIDER" }), "OVERVIEW") });
    expect(html).toContain("Explicación asistida y verificada");
    expect(html).not.toMatch(/FAKE_PROVIDER|hidden-|provider_name|model_name/);
  });
  it.each([
    "La institución registra 0 señales abiertas: 0 de prioridad alta, 0 media y 0 baja.",
    "La institución registra 3 señales abiertas: 0 de prioridad alta, 0 media y 3 bajas.",
  ])("preserves backend zero/low aggregate semantics: %s", summary => {
    expect(render({ briefing: projectMentorBriefing(run("OVERVIEW", { summary }), "OVERVIEW") })).toContain(summary);
  });
  it("hides old evidence during loading, denial, and refresh errors", () => {
    for (const props of [{ loading: true }, { allowed: false }, { error: new ApiError(404, "hidden snapshot") }]) {
      const html = render(props);
      expect(html).not.toContain("3 open signals");
      expect(html).not.toContain("2026-09-19");
    }
    expect(render({ loading: true })).toContain('aria-busy="true"');
    expect(render({ loading: true })).toContain("Preparando el resumen");
  });
  it.each([401, 403, 404, 422, 500])("presents safe HTTP %s without raw backend errors", status => {
    const error = new ApiError(status, "secret stack trace with hidden snapshot ID");
    expect(render({ error })).toContain(mentorErrorMessage(error));
    expect(render({ error })).not.toMatch(/secret|stack trace|hidden snapshot/);
    if (status === 404) expect(render({ error })).toContain("No hay evidencia institucional disponible");
  });
  it("never caches or renders internal metadata and escapes evidence text", () => {
    const briefing = projectMentorBriefing(run("OVERVIEW", { summary: "<script>alert('data')</script>" }), "OVERVIEW");
    expect(JSON.stringify(briefing)).not.toContain("hidden-");
    const html = render({ briefing });
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).not.toMatch(/hidden-|sha256|provider_name|model_name|raw_prompt|raw_response|source_entity_id/);
  });
  it.each([
    { status: "FAILED", output: null },
    run("PRIORITIES"),
    run("OVERVIEW", { key_findings: [{ text: "Unknown", evidence_refs: ["ev_02"] }] }),
    run("OVERVIEW", { key_findings: [{ text: "Duplicate", evidence_refs: ["ev_01", "ev_01"] }] }),
    run("OVERVIEW", { freshness: "UNRECOGNIZED" }),
    run("OVERVIEW", { evidence_refs: [] }),
  ])("rejects incomplete or mismatched responses", response => {
    expect(() => projectMentorBriefing(response, "OVERVIEW")).toThrow();
  });
});

describe("Mentor API and query isolation", () => {
  function mockFetch() {
    vi.stubGlobal("sessionStorage", { getItem: () => "test-session" });
    const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
      const { briefing_focus } = JSON.parse(String(init.body));
      return new Response(JSON.stringify(run(briefing_focus)), { status: 201 });
    });
    vi.stubGlobal("fetch", fetcher);
    return fetcher;
  }
  it("switches focuses using only the existing endpoint and exact typed input", async () => {
    const fetcher = mockFetch();
    const client = new QueryClient();
    try {
      for (const focus of MENTOR_FOCUSES) {
        const result = await client.fetchQuery(mentorQueryOptions(context, focus));
        expect(result.briefing_focus).toBe(focus);
      }
      expect(fetcher).toHaveBeenCalledTimes(3);
      fetcher.mock.calls.forEach(([url, init], index) => {
        expect(url).toBe("/api/v1/agents/mentor_institution_briefing/runs");
        expect(JSON.parse(String(init.body))).toEqual({ briefing_focus: MENTOR_FOCUSES[index] });
        expect(init.method).toBe("POST");
        expect(new Headers(init.headers).get("Authorization")).toBe("Bearer test-session");
      });
    } finally { client.clear(); }
  });
  it("isolates tenant, principal, permissions, and focus; retries no requests", () => {
    const initial = mentorQueryOptions(context, "OVERVIEW");
    for (const other of [
      { ...context, tenant: { ...context.tenant, institution_id: "other" } },
      { ...context, user: { ...context.user, user_id: "other" } },
      { ...context, permissions: [] },
    ]) expect(mentorQueryOptions(other, "OVERVIEW").queryKey).not.toEqual(initial.queryKey);
    expect(mentorQueryOptions(context, "PRIORITIES").queryKey).not.toEqual(initial.queryKey);
    expect(initial.retry).toBe(false);
    expect(initial.gcTime).toBe(0);
    expect(initial.staleTime).toBe(0);
    expect(mentorQueryOptions({ ...context, permissions: [] }, "OVERVIEW").enabled).toBe(false);
  });
  it("does not retain an old focus result while a new request is pending", async () => {
    mockFetch();
    const client = new QueryClient();
    const observer = new QueryObserver(client, mentorQueryOptions(context, "OVERVIEW"));
    const unsubscribe = observer.subscribe(() => {});
    try {
      await observer.refetch();
      expect(observer.getCurrentResult().data?.briefing_focus).toBe("OVERVIEW");
      observer.setOptions(mentorQueryOptions(context, "PRIORITIES"));
      expect(observer.getCurrentResult().isPending).toBe(true);
      expect(observer.getCurrentResult().data).toBeUndefined();
      await observer.refetch();
      expect(observer.getCurrentResult().data?.briefing_focus).toBe("PRIORITIES");
    } finally { unsubscribe(); client.clear(); }
  });
  it("rechecks the backend on refresh and hides a disappeared snapshot", async () => {
    const fetcher = mockFetch();
    const client = new QueryClient();
    const observer = new QueryObserver(client, mentorQueryOptions(context, "OVERVIEW"));
    const unsubscribe = observer.subscribe(() => {});
    try {
      await observer.refetch();
      fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "hidden evidence" }), { status: 404 }));
      const result = await observer.refetch();
      expect(result.isError).toBe(true);
      expect(render({ briefing: result.data, error: result.error })).not.toContain("3 open signals");
      expect(render({ briefing: result.data, error: result.error })).toContain("No hay evidencia institucional disponible");
    } finally { unsubscribe(); client.clear(); }
  });
});
