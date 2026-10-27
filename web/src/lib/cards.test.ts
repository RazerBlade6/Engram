import { describe, expect, it } from "vitest";

import { clozeParts, sourceLabel } from "./cards";

describe("clozeParts", () => {
  it("splits out the hidden part", () => {
    expect(clozeParts("The {{nucleus}} stores DNA.")).toEqual([
      { text: "The ", hidden: false },
      { text: "nucleus", hidden: true },
      { text: " stores DNA.", hidden: false },
    ]);
  });
});

describe("sourceLabel", () => {
  it("names the section and page", () => {
    expect(
      sourceLabel({
        quote: "q",
        heading_path: ["Chapter 1", "1.2 Cells"],
        page: 23,
      }),
    ).toBe("1.2 Cells, page 23");
    expect(sourceLabel({ quote: "q", heading_path: [], page: null })).toBe("");
  });
});
