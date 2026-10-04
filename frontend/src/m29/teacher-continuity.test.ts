import { beforeEach, describe, expect, it, vi } from "vitest";

import { teacherContinuityQuery } from "./teacher-continuity";
import { appDeepLink } from "./teacher-continuity-page";

describe("M29-2 teacher continuity client", () => {
  beforeEach(() => {
    const storage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    vi.stubGlobal("sessionStorage", storage);
  });

  it("uses the bounded teacher continuity read endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], has_more: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetcher);

    await teacherContinuityQuery({ limit: 25 });

    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/continuity/worklist?limit=25");
  });

  it("uses a bounded page size", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], has_more: false }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetcher);

    await teacherContinuityQuery({ limit: 25 });

    const path = String(fetcher.mock.calls[0][0]);
    expect(path).toContain("limit=25");
    expect(path).not.toContain("cursor");
  });

  it("keeps authoritative links inside the configured React base path", () => {
    expect(appDeepLink("/m21/interventions/intervention-1")).toBe(
      "/app/m21/interventions/intervention-1",
    );
    expect(appDeepLink("/app/accountability/cases/case-1")).toBe(
      "/app/accountability/cases/case-1",
    );
  });
});
