import { describe, expect, it } from "vitest";

import { findModule, modulesForContext } from "./navigation";
import type { UiBootstrap } from "./types/bootstrap";

function context(permissions: string[]): UiBootstrap {
  return {
    user: {
      user_id: "00000000-0000-0000-0000-000000000001",
      display_name: "Control Plane Demo",
      login_email: "control@example.test",
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
    capabilities: {},
    profiles: {
      staff: true,
      student: false,
      guardian: false,
    },
  };
}

describe("M19 institution control-plane navigation", () => {
  it("exposes Control Plane only with control_plane.view", () => {
    expect(
      modulesForContext(context(["control_plane.view"])).map(
        (item) => item.id,
      ),
    ).toEqual(["control-plane"]);

    expect(
      modulesForContext(context(["admin.console.access"])).map(
        (item) => item.id,
      ),
    ).not.toContain("control-plane");
  });

  it("resolves the stable control-plane module contract", () => {
    const module = findModule("control-plane");
    expect(module?.permission).toBe("control_plane.view");
    expect(module?.legacyPath).toBe(
      "/api/v1/control-plane/dashboard",
    );
  });
});
