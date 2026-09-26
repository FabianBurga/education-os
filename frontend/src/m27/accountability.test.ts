import { beforeEach, describe, expect, it, vi } from "vitest";

import { commandHashes, queueQuery, recordDecision } from "./accountability";

describe("M27 accountability experience client", () => {
  beforeEach(() => {
    const storage = { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() };
    vi.stubGlobal("sessionStorage", storage);
  });

  it("uses the backend queue boundary and preserves bounded filters", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], next_cursor: null, generated_at: "now" }), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await queueQuery({ reason: "REVIEW_REQUIRED", unassigned: false, compliance_status: "" });
    expect(String(fetcher.mock.calls[0][0])).toContain("/api/v1/accountability/queue?");
    expect(String(fetcher.mock.calls[0][0])).toContain("reason=REVIEW_REQUIRED");
    expect(String(fetcher.mock.calls[0][0])).not.toContain("unassigned=false");
  });

  it("creates stable-shaped idempotency and provenance hashes", async () => {
    const hashes = await commandHashes("review", "case-1");
    expect(hashes.idempotency_key).toMatch(/^[0-9a-f]{64}$/);
    expect(hashes.provenance_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(hashes.idempotency_key).not.toBe(hashes.provenance_sha256);
  });

  it("sends decision commands to M27 and never to the M21 mutation path", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ command: "DECISION_RECORDED" }), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await recordDecision("case-1", { decision_type: "CREATE_INTERVENTION" });
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/accountability/cases/case-1/decision");
    expect(fetcher.mock.calls[0][0]).not.toContain("/interventions");
  });
});
