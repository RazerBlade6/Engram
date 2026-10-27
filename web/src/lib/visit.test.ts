import { beforeEach, describe, expect, it } from "vitest";

import { pageOf } from "./usage";
import { IDLE_MS, currentVisit } from "./visit";

describe("currentVisit", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    globalThis.sessionStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    } as Storage;
  });

  it("keeps one visit while active and starts a new one after a long idle", () => {
    const first = currentVisit(0);
    expect(currentVisit(IDLE_MS - 1)).toBe(first);
    // Activity keeps it going.
    expect(currentVisit(2 * IDLE_MS - 2)).toBe(first);
    expect(currentVisit(4 * IDLE_MS)).not.toBe(first);
  });
});

describe("pageOf", () => {
  it("names the page without the ids in it", () => {
    expect(pageOf("/courses/4f1c2a9e-1b2c-4d3e-8f90-123456789abc")).toBe("/courses/[id]");
    expect(pageOf("/admin/materials/4F1C2A9E-1B2C-4D3E-8F90-123456789ABC")).toBe("/admin/materials/[id]");
    expect(pageOf("/")).toBe("/");
    expect(pageOf("/Calendar")).toBe("/calendar");
  });
});
