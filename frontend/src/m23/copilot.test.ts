import { describe, expect, it } from "vitest";
import { copilotCapabilities, isTeacherAdvisoryOnly } from "./copilot";
describe("M23 governed Copilot client", () => {
  it("derives access exclusively from effective permissions", () => { expect(copilotCapabilities(["copilot.use"])).toEqual({ canUse: true, canApprove: false, canManage: false }); });
  it("keeps a use-only context on the student-targeted advisory surface", () => { expect(isTeacherAdvisoryOnly(["copilot.use"])).toBe(true); expect(isTeacherAdvisoryOnly(["copilot.use", "copilot.action.approve"])).toBe(false); });
});
