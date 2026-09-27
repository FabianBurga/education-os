import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppContextProvider } from "../app-context";
import type { UiBootstrap } from "../types/bootstrap";
import { StudentRecordsPage, StudentRecordEditor } from "./student-records-page";

const record = {
  id: "00000000-0000-0000-0000-000000000001",
  display_name: "Estudiante Sintético",
  student_code: "SYN-001",
  status: "ACTIVE" as const,
  updated_at: "2026-01-01T00:00:00Z",
};

function bootstrap(permissions: string[]): UiBootstrap {
  return {
    user: { user_id: "u1", display_name: "Operador", login_email: "operator@test.invalid" },
    tenant: { organization_id: "o1", organization_name: "Synthetic Org", institution_id: "i1", institution_name: "Synthetic School", institution_type: "PRIVATE" },
    roles: ["SYSTEM_ADMIN"], permissions, capabilities: {}, profiles: { staff: true, student: false, guardian: false },
  };
}

function renderPage(permissions: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderToStaticMarkup(createElement(QueryClientProvider, { client: queryClient },
    createElement(AppContextProvider, {
      value: { bootstrap: bootstrap(permissions), signOut: () => undefined },
      children: createElement(StudentRecordsPage),
    })));
}

describe("M28-1 student record experience", () => {
  it("renders a bounded, accessible list/detail loading path from read permission", () => {
    const html = renderPage(["students.read"]);
    expect(html).toContain("Registros estudiantiles");
    expect(html).toContain("Cargando registros");
    expect(html).toContain("Lista de estudiantes");
    expect(html).toContain("Detalle estudiantil");
  });

  it("does not treat a SYSTEM_ADMIN role as student read authority", () => {
    const html = renderPage([]);
    expect(html).toContain("students.read");
    expect(html).not.toContain("Lista de estudiantes");
  });

  it("renders editable controls only with manage capability and keeps fields labeled", () => {
    const html = renderToStaticMarkup(createElement(StudentRecordEditor, {
      record, canManage: true, saving: false, error: null, onSave: () => undefined,
    }));
    expect(html).toContain("Código estudiantil");
    expect(html).toContain("Estado del perfil");
    expect(html).toContain("Guardar cambios");
    const readOnly = renderToStaticMarkup(createElement(StudentRecordEditor, {
      record, canManage: false, saving: false, error: null, onSave: () => undefined,
    }));
    expect(readOnly).toContain("requiere students.manage");
    expect(readOnly).not.toContain("Guardar cambios");
  });
});
