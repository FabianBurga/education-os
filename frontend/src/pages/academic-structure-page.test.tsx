import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppContextProvider } from "../app-context";
import { academicCapabilities } from "../m28/academic-structure";
import type { UiBootstrap } from "../types/bootstrap";
import { AcademicStructurePage } from "./academic-structure-page";

function renderPage(permissions: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const bootstrap: UiBootstrap = {
    user: { user_id: "u1", display_name: "Synthetic operator", login_email: "operator@test.invalid" },
    tenant: { organization_id: "o1", organization_name: "Synthetic Org", institution_id: "i1", institution_name: "Synthetic School", institution_type: "PRIVATE" },
    roles: ["SYSTEM_ADMIN"], permissions, capabilities: {}, profiles: { staff: true, student: false, guardian: false },
  };
  return renderToStaticMarkup(createElement(QueryClientProvider, { client: queryClient },
    createElement(AppContextProvider, { value: { bootstrap, signOut: () => undefined }, children: createElement(AcademicStructurePage) })));
}

describe("M28-3 academic structure workspace", () => {
  it("requires effective permission rather than SYSTEM_ADMIN role", () => {
    expect(academicCapabilities([])).toEqual({ canRead: false, canManage: false, canAssign: false });
    const html = renderPage([]);
    expect(html).toContain("academics.read");
    expect(html).not.toContain("Períodos");
  });

  it("renders bounded setup panels for an explicitly authorized operator", () => {
    expect(academicCapabilities(["academics.read", "academics.manage"])).toEqual({ canRead: true, canManage: true, canAssign: false });
    const html = renderPage(["academics.read", "academics.manage"]);
    expect(html).toContain("Estructura académica");
    expect(html).toContain("Crear período planificado");
    expect(html).toContain("Ofertas de curso");
    expect(html).not.toContain("Asignación docente");
  });

  it("requires students.read before exposing roster records", () => {
    const withoutStudentRead = renderPage(["academics.read"]);
    expect(withoutStudentRead).toContain("Roster vigente por sección");
    expect(withoutStudentRead).toContain("students.read");
    const authorized = renderPage(["academics.read", "students.read"]);
    expect(authorized).toContain("Sección");
  });
});
