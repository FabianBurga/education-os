import { describe, expect, it } from "vitest";

import {
  findModule,
  moduleCapabilityState,
  modulesForContext,
} from "./navigation";
import type { UiBootstrap } from "./types/bootstrap";

function context(
  permissions: string[],
  capabilities: Record<string, boolean> = {},
): UiBootstrap {
  return {
    user: {
      user_id: "00000000-0000-0000-0000-000000000001",
      display_name: "Persona Demo",
      login_email: "demo@example.test",
    },
    tenant: {
      organization_id: "00000000-0000-0000-0000-000000000002",
      organization_name: "Organización Demo",
      institution_id: "00000000-0000-0000-0000-000000000003",
      institution_name: "Institución Demo",
      institution_type: "PRIVATE",
    },
    roles: [],
    permissions,
    capabilities,
    profiles: {
      staff: true,
      student: false,
      guardian: false,
    },
  };
}

describe("M15 role-aware navigation", () => {
  it("shows only modules backed by granted permissions", () => {
    const result = modulesForContext(
      context([
        "admin.console.access",
        "communications.console.access",
      ]),
    );

    expect(result.map((item) => item.id)).toEqual([
      "administration",
      "communications",
    ]);
  });

  it("keeps finance visible when permission exists but capability is disabled", () => {
    const bootstrap = context(
      ["finance.console.access"],
      { "finance.billing": false },
    );
    const modules = modulesForContext(bootstrap);

    expect(modules.map((item) => item.id)).toEqual(["finance"]);
    expect(moduleCapabilityState(modules[0], bootstrap)).toBe("disabled");
  });

  it("shows Copilot only when its explicit use permission is granted", () => {
    expect(
      modulesForContext(context(["copilot.use"])).map((item) => item.id),
    ).toEqual(["copilot"]);
    expect(
      modulesForContext(context(["copilot.action.approve"])),
    ).toEqual([]);
  });

  it("resolves stable module ids used by the router", () => {
    expect(findModule("guardian")?.permission).toBe(
      "guardian.console.access",
    );
    expect(findModule("missing")).toBeUndefined();
  });
});
