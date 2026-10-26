import { describe, expect, it } from "vitest";

import { apiUrl } from "./api";

describe("apiUrl", () => {
  it("joins base and path with a single slash", () => {
    expect(apiUrl("/health", "http://api.test/")).toBe("http://api.test/health");
    expect(apiUrl("health", "http://api.test")).toBe("http://api.test/health");
  });
});
