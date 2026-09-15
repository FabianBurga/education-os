import { describe, expect, it } from "vitest";

import {
  allowedActionTransitions,
  allowedInterventionTransitions,
  canCompleteAction,
  interventionWorkspaceCapabilities,
  minimumFollowUpSensitivity,
} from "./intervention-workspace";

describe("M21-F1.4 intervention workspace foundation", () => {
  it("derives write controls from explicit permissions", () => {
    expect(
      interventionWorkspaceCapabilities([
        "intervention.read",
        "intervention.action.manage",
        "intervention.followup.create",
      ]),
    ).toEqual({
      canRead: true,
      canUpdate: false,
      canAssign: false,
      canManageActions: true,
      canCreateFollowUp: true,
      canResolve: false,
      canClose: false,
    });
  });

  it("mirrors the intervention lifecycle contract", () => {
    expect(allowedInterventionTransitions("OPEN")).toEqual([
      "IN_PROGRESS",
    ]);
    expect(allowedInterventionTransitions("IN_PROGRESS")).toEqual([
      "MONITORING",
    ]);
    expect(allowedInterventionTransitions("RESOLVED")).toEqual([
      "IN_PROGRESS",
      "MONITORING",
    ]);
    expect(allowedInterventionTransitions("CLOSED")).toEqual([]);
  });

  it("mirrors the action lifecycle contract", () => {
    expect(allowedActionTransitions("OPEN")).toEqual([
      "ACKNOWLEDGED",
      "IN_PROGRESS",
      "CANCELLED",
    ]);
    expect(canCompleteAction("ACKNOWLEDGED")).toBe(true);
    expect(canCompleteAction("IN_PROGRESS")).toBe(true);
    expect(canCompleteAction("OPEN")).toBe(false);
  });

  it("does not lower follow-up sensitivity below the parent", () => {
    expect(minimumFollowUpSensitivity("GENERAL")).toBe("GENERAL");
    expect(minimumFollowUpSensitivity("RESTRICTED")).toBe(
      "RESTRICTED",
    );
    expect(minimumFollowUpSensitivity("CONFIDENTIAL")).toBe(
      "CONFIDENTIAL",
    );
  });
});
