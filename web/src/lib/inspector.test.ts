import { describe, expect, it } from "vitest";

import { boxStyle, emptyPages, pageRanges, sectionsOnPage, type Section } from "./inspector";

const section = (ordinal: number, level: number, start: number, end: number): Section => ({
  id: String(ordinal),
  parent_id: null,
  ordinal,
  level,
  title: `Section ${ordinal}`,
  page_start: start,
  page_end: end,
});

describe("boxStyle", () => {
  it("converts PDF points to percentages of the page", () => {
    expect(boxStyle([61.2, 79.2, 306, 396], 612, 792)).toEqual({
      left: "10%",
      top: "10%",
      width: "40%",
      height: "40%",
    });
  });
});

describe("sectionsOnPage", () => {
  it("returns every section whose range covers the page, in order", () => {
    const sections = [section(0, 1, 1, 10), section(1, 2, 1, 4), section(2, 2, 5, 10)];
    expect(sectionsOnPage(sections, 4).map((s) => s.ordinal)).toEqual([0, 1]);
    expect(sectionsOnPage(sections, 5).map((s) => s.ordinal)).toEqual([0, 2]);
    expect(sectionsOnPage(sections, 11)).toEqual([]);
  });
});

describe("emptyPages and pageRanges", () => {
  it("finds pages with no extracted content and groups them", () => {
    const stats = [3, 4, 8].map((page) => ({ page, text: 1, tables: 0, figures: 0 }));
    const empty = emptyPages(10, stats);
    expect(empty).toEqual([1, 2, 5, 6, 7, 9, 10]);
    expect(pageRanges(empty)).toEqual([
      { start: 1, end: 2 },
      { start: 5, end: 7 },
      { start: 9, end: 10 },
    ]);
  });
});
