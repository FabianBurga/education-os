import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  CSV_IMPORT_CONTRACT,
  canApplyPreview,
  canReadAuditEvents,
  csvFileIsAccepted,
  integrationCapabilities,
  integrationErrorMessage,
  itemErrorMessage,
  previewStudentEnrollmentCsv,
} from "./integrations";
import { ApiError } from "../lib/api";

const PAGE = readFileSync(resolve("src/pages/integration-workspace-page.tsx"), "utf8");
const CLIENT = readFileSync(resolve("src/m24/integrations.ts"), "utf8");

afterEach(() => vi.unstubAllGlobals());

describe("M24 Integration Hub client and permission surface", () => {
  it("derives every operator capability from effective permissions only", () => {
    expect(integrationCapabilities(["integrations.view"])).toEqual({ canView: true, canManage: false, canRun: false, canAudit: false });
    expect(integrationCapabilities(["integrations.view", "integrations.manage", "integrations.run", "integrations.audit.read"])).toEqual({ canView: true, canManage: true, canRun: true, canAudit: true });
    expect(integrationCapabilities([]).canView).toBe(false);
    expect(PAGE).not.toContain("SYSTEM_ADMIN");
    expect(PAGE).not.toContain("TEACHER");
  });

  it("keeps the frozen CSV contract and accepts only bounded CSV files", () => {
    expect(CSV_IMPORT_CONTRACT.required).toEqual(["external_student_id", "given_names", "family_names", "academic_period_code", "campus_id"]);
    expect(CSV_IMPORT_CONTRACT.optional).toEqual(["student_code", "enrollment_number", "enrollment_status", "enrolled_on"]);
    expect(csvFileIsAccepted({ name: "pilot.csv", size: 1_000_000 } as File)).toBe(true);
    expect(csvFileIsAccepted({ name: "pilot.xlsx", size: 100 } as File)).toBe(false);
    expect(csvFileIsAccepted({ name: "pilot.csv", size: 1_000_001 } as File)).toBe(false);
  });

  it("maps stable machine codes to safe Spanish operator messages without raw server output", () => {
    expect(integrationErrorMessage(new ApiError(422, "ACADEMIC_PERIOD_NOT_FOUND"))).toBe("No se encontró el período académico indicado.");
    expect(itemErrorMessage("ACADEMIC_PERIOD_NOT_FOUND")).toBe("No se encontró el período académico indicado. Código: ACADEMIC_PERIOD_NOT_FOUND");
    expect(itemErrorMessage("EXTERNAL_ID_DUPLICATE")).toContain("referencia existente");
    expect(itemErrorMessage("UNEXPECTED_CODE")).toContain("Código: UNEXPECTED_CODE");
  });

  it("uses only frozen M24 endpoints and keeps preview separate from explicit apply", () => {
    for (const path of ["/connectors", "/csv/student-enrollment/preview", "/runs?limit=100", "/runs/${runId}/items", "/runs/${runId}/events", "/runs/${runId}/apply"]) expect(CLIENT).toContain(path);
    expect(PAGE).toContain("data-testid=\"m24-preview\"");
    expect(PAGE).toContain("data-testid=\"m24-request-apply\"");
    expect(PAGE).toContain("data-testid=\"m24-confirm-apply\"");
    expect(PAGE).toContain("Solo las filas válidas serán aplicadas");
  });

  it("sends exactly one bounded CSV preview request and never applies from the preview client", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run: {}, total_rows: 0, valid_rows: 0, invalid_rows: 0, conflict_rows: 0 }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("sessionStorage", { getItem: () => null });
    await previewStudentEnrollmentCsv("connector-1", { name: "pilot.csv", size: 12 } as File);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/integrations/connectors/connector-1/csv/student-enrollment/preview");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(fetchMock.mock.calls[0][1].headers.get("Content-Type")).toBe("text/csv");
  });

  it("requires a validated preview for apply and an audit permission for events", () => {
    expect(canApplyPreview(true, "run-1", "run-1", "VALIDATED")).toBe(true);
    expect(canApplyPreview(true, "run-1", "run-1", "COMPLETED")).toBe(false);
    expect(canApplyPreview(false, "run-1", "run-1", "VALIDATED")).toBe(false);
    expect(canReadAuditEvents(true, "run-1")).toBe(true);
    expect(canReadAuditEvents(false, "run-1")).toBe(false);
  });

  it("does not render raw CSV detail or call audit events without audit permission", () => {
    expect(PAGE).not.toContain("dangerouslySetInnerHTML");
    expect(PAGE).not.toContain("item.detail");
    expect(PAGE).toContain("canReadAuditEvents(capabilities.canAudit, currentRunId)");
    expect(PAGE).toContain("accept=\".csv,text/csv\"");
  });
});
