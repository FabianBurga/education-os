import { describe, expect, it } from "vitest";

import {
  buildStudentInterventionsPath,
  buildStudentTimelinePath,
  student360Capabilities,
  timelineCategoryTone,
} from "./student-360";

describe("M21-F1.3 Student 360 frontend foundation", () => {
  it("builds backend-compatible timeline filters", () => {
    expect(
      buildStudentTimelinePath(
        "00000000-0000-0000-0000-000000000123",
        {
          category: "SIGNAL",
          sensitivity: "RESTRICTED",
          beforePosition: 42,
        },
      ),
    ).toBe(
      "/api/v1/student-timeline/students/" +
        "00000000-0000-0000-0000-000000000123?" +
        "limit=50&before_position=42&category=SIGNAL&" +
        "sensitivity=RESTRICTED",
    );
  });

  it("builds the student intervention query", () => {
    expect(
      buildStudentInterventionsPath(
        "00000000-0000-0000-0000-000000000123",
      ),
    ).toBe(
      "/api/v1/interventions/students/" +
        "00000000-0000-0000-0000-000000000123?limit=50",
    );
  });

  it("derives Student 360 capabilities from permissions only", () => {
    expect(
      student360Capabilities([
        "student_timeline.read",
        "intervention.read",
      ]),
    ).toEqual({
      canReadTimeline: true,
      canReadInterventions: true,
      canReadSuggestions: false,
    });
  });

  it("visually distinguishes signal/intervention/outcome events", () => {
    expect(timelineCategoryTone("SIGNAL")).toBe("warning");
    expect(timelineCategoryTone("INTERVENTION")).toBe("danger");
    expect(timelineCategoryTone("OUTCOME")).toBe("success");
    expect(timelineCategoryTone("ACADEMIC")).toBe("neutral");
  });
});
