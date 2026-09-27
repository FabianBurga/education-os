import { describe, expect, it } from "vitest";

import { ApiError } from "../lib/api";
import { enrollmentCapabilities, studentRecordCapabilities, studentRecordErrorMessage } from "./student-records";

describe("M28-1 student record capabilities and safe errors", () => {
  it("uses only effective permission keys, never role names", () => {
    expect(studentRecordCapabilities(["RECTOR"])).toEqual({ canRead: false, canManage: false });
    expect(studentRecordCapabilities(["students.read"])).toEqual({ canRead: true, canManage: false });
    expect(studentRecordCapabilities(["students.manage"])).toEqual({ canRead: false, canManage: true });
  });

  it.each([
    [403, "No tienes permiso"],
    [404, "no está disponible"],
    [409, "cambió o tiene una matrícula activa"],
    [422, "Revisa los campos"],
  ])("maps HTTP %s to a bounded operator message", (status, expected) => {
    expect(studentRecordErrorMessage(new ApiError(status, "private backend detail"))).toContain(expected);
  });

  it("never shows server trace text for unclassified or network failures", () => {
    expect(studentRecordErrorMessage(new ApiError(500, "SQL password and trace"))).toBe(
      "No fue posible completar la solicitud. Inténtalo de nuevo.",
    );
    expect(studentRecordErrorMessage(new Error("network internals"))).toBe(
      "No fue posible completar la solicitud. Inténtalo de nuevo.",
    );
  });
});

describe("M28-2 enrollment capability boundary", () => {
  it("uses effective permissions and never grants lifecycle actions from a role label", () => {
    expect(enrollmentCapabilities(["SYSTEM_ADMIN", "RECTOR"])).toEqual({ canRead: false, canManage: false });
    expect(enrollmentCapabilities(["students.read"])).toEqual({ canRead: false, canManage: false });
    expect(enrollmentCapabilities(["enrollments.read"])).toEqual({ canRead: true, canManage: false });
    expect(enrollmentCapabilities(["enrollments.read", "enrollments.manage"])).toEqual({ canRead: true, canManage: true });
  });
});
