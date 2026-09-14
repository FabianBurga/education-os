import { describe, expect, it } from "vitest";

import {
  buildSuggestionListPath,
  isSuggestionReviewable,
  reviewNoteError,
  suggestionCapabilities,
} from "./suggestions";

describe("M21-F1 suggestion frontend foundation", () => {
  it("builds backend-compatible suggestion filters", () => {
    expect(
      buildSuggestionListPath({
        status: "PENDING",
        severity: "HIGH",
        sensitivity: "RESTRICTED",
        studentProfileId:
          " 00000000-0000-0000-0000-000000000123 ",
      }),
    ).toBe(
      "/api/v1/interventions/suggestions?" +
        "limit=50&status=PENDING&severity=HIGH&" +
        "sensitivity=RESTRICTED&" +
        "student_profile_id=00000000-0000-0000-0000-000000000123",
    );
  });

  it("derives UX capabilities only from explicit backend permissions", () => {
    expect(
      suggestionCapabilities([
        "intervention.suggestion.read",
        "intervention.suggestion.generate",
      ]),
    ).toEqual({
      canRead: true,
      canGenerate: true,
      canReview: false,
    });
  });

  it("keeps human review limited to pending suggestions", () => {
    expect(isSuggestionReviewable("PENDING")).toBe(true);
    expect(isSuggestionReviewable("ACCEPTED")).toBe(false);
    expect(isSuggestionReviewable("DISMISSED")).toBe(false);
    expect(isSuggestionReviewable("EXPIRED")).toBe(false);
  });

  it("requires a bounded human review note", () => {
    expect(reviewNoteError("   ")).toMatch(/nota de revisión/i);
    expect(reviewNoteError("Revisado por coordinación.")).toBeNull();
    expect(reviewNoteError("x".repeat(1001))).toMatch(/1000/);
  });
});
