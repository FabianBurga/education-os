import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppContextProvider } from "./app-context";
import { WorkspacePage } from "./pages/workspace-page";
import type { UiBootstrap } from "./types/bootstrap";

const base: UiBootstrap = {
  user: { user_id: "teacher-1", display_name: "Docente", login_email: "teacher@demo" },
  tenant: {
    organization_id: "org-1",
    organization_name: "Education OS Demo",
    institution_id: "institution-1",
    institution_name: "Unidad Educativa Demostración",
    institution_type: "PUBLIC",
  },
  roles: ["TEACHER"],
  permissions: ["teacher.console.access"],
  capabilities: {},
  profiles: { staff: true, student: false, guardian: false },
};

function render(capabilities: UiBootstrap["capabilities"] = {}) {
  return renderToStaticMarkup(
    <AppContextProvider value={{ bootstrap: { ...base, capabilities }, signOut: () => {} }}>
      <WorkspacePage moduleId="teacher" />
    </AppContextProvider>,
  );
}

describe("Teacher workspace routing", () => {
  it("opens the operational console when offline capability is unavailable", () => {
    expect(render()).toContain('data-testid="teacher-operational-redirect"');
    expect(render()).not.toContain("Modo docente sin conexión deshabilitado");
  });

  it("preserves the offline workspace when its capability is enabled", () => {
    expect(render({ "teacher.offline_pwa": true })).toContain('data-testid="teacher-pwa-page"');
  });
});
