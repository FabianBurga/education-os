import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AppContextProvider } from "../app-context";
import type { UiBootstrap } from "../types/bootstrap";
import {
  GuardianContinuityCard,
  guardianNoticeScopeLabel,
  selectCuratedGuardianNotice,
  type GuardianContinuityNotice,
} from "./guardian-continuity";

const notice = (overrides: Partial<GuardianContinuityNotice> = {}): GuardianContinuityNotice => ({
  notice_id: "notice-1",
  student_profile_id: "student-1",
  notice_type: "ACADEMIC",
  title: "Actualización académica",
  requires_acknowledgement: true,
  published_at: "2026-01-01T00:00:00Z",
  acknowledged_at: null,
  scope: "STUDENT",
  ...overrides,
});

function renderCard(permissions: string[]) {
  const bootstrap: UiBootstrap = {
    user: { user_id: "guardian-user", display_name: "Guardian", login_email: "guardian@test.invalid" },
    tenant: { organization_id: "org-1", organization_name: "Org", institution_id: "inst-1", institution_name: "School", institution_type: "PUBLIC" },
    roles: ["GUARDIAN"],
    permissions,
    capabilities: {},
    profiles: { staff: false, student: false, guardian: true },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: queryClient },
      createElement(AppContextProvider, {
        value: { bootstrap, signOut: () => undefined },
        children: createElement(GuardianContinuityCard),
      })),
  );
}

describe("M29-3 curated guardian continuity", () => {
  it("does not render a notice surface without current notice visibility", () => {
    expect(renderCard(["guardian.console.access"])).not.toContain("guardian-continuity-card");
  });

  it("renders a bounded family surface without internal domain categories", () => {
    const html = renderCard(["guardian.console.access", "guardian.notices.view"]);
    expect(html).toContain("guardian-continuity-card");
    expect(html).toContain("Continuidad familiar");
    expect(html).not.toContain("intervention");
    expect(html).not.toContain("obligation");
    expect(html).not.toContain("risk");
  });

  it("selects only the newest acknowledgement-required notice", () => {
    const selected = selectCuratedGuardianNotice([
      notice({ notice_id: "older", published_at: "2026-01-01T00:00:00Z" }),
      notice({ notice_id: "newer", published_at: "2026-02-01T00:00:00Z" }),
      notice({ notice_id: "informational", requires_acknowledgement: false }),
    ]);

    expect(selected?.notice_id).toBe("newer");
  });

  it("does not expose a student identifier when no authorized student label exists", () => {
    const selected = notice({ student_profile_id: "hidden-student" });
    expect(guardianNoticeScopeLabel(selected, [])).toBe("Aviso para estudiante autorizado");
    expect(guardianNoticeScopeLabel(selected, [])).not.toContain("hidden-student");
  });

  it("keeps institution-wide notices separate from student continuity", () => {
    const selected = notice({ student_profile_id: null, scope: "INSTITUTION" });
    expect(guardianNoticeScopeLabel(selected, [])).toBe("Aviso institucional");
  });
});
