import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoEntrance, PERSONAS, demoRequest, clearDemoBrowserState } from "./gateway";

afterEach(() => vi.unstubAllGlobals());

describe("protected demonstration entrance", () => {
  it("does not show profile choices before the outer gate", () => {
    const html = renderToStaticMarkup(<DemoEntrance status={{ demo: true, entrance: false, alias: null }} refresh={() => {}} />);
    expect(html).toContain("Código de acceso");
    expect(html).toContain('type="password"');
    expect(html).not.toContain("Coordinación académica");
    expect(html).not.toContain("Bearer");
  });
  it("offers exactly the five aliases with meaningful labels and no identity input", () => {
    expect(Object.keys(PERSONAS)).toEqual(["RECTOR", "COORDINATION", "TEACHER", "STUDENT", "GUARDIAN"]);
    const html = renderToStaticMarkup(<DemoEntrance status={{ demo: true, entrance: true, alias: null }} refresh={() => {}} />);
    for (const label of Object.values(PERSONAS)) expect(html).toContain(label);
    expect(html).not.toContain("<input");
    expect(html).not.toMatch(/token|UUID|organization_id|institution_id|user_id|permission/i);
  });
  it("sends only an alias in a same-origin POST body without bearer credentials", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ alias: "STUDENT" }) });
    vi.stubGlobal("fetch", fetch);
    await demoRequest("session", { alias: "STUDENT" });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/demo/session");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBe('{"alias":"STUDENT"}');
    expect(init.headers).not.toHaveProperty("Authorization");
  });
  it("keeps the entrance code out of URLs and hides backend error details", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: false, text: async () => "private database error" });
    vi.stubGlobal("fetch", fetch);
    await expect(demoRequest("entrance", { code: "test-only-code" })).rejects.toThrow("No fue posible acceder");
    expect(fetch.mock.calls[0][0]).toBe("/api/demo/entrance");
  });
  it("purges prior bearer, bootstrap and offline state before another persona", async () => {
    const removeItem = vi.fn();
    vi.stubGlobal("sessionStorage", { removeItem });
    const request: { onsuccess?: () => void } = {};
    const deleteDatabase = vi.fn(() => { queueMicrotask(() => request.onsuccess?.()); return request; });
    vi.stubGlobal("indexedDB", { deleteDatabase });
    await clearDemoBrowserState();
    expect(removeItem).toHaveBeenCalledWith("education_os_access_token");
    expect(removeItem).toHaveBeenCalledWith("education_os_bootstrap_cache");
    expect(removeItem).toHaveBeenCalledWith("education_os_coord_token");
    expect(deleteDatabase).toHaveBeenCalledWith("education-os-teacher-offline");
  });
});
