import { describe, expect, it } from "vitest";

import { pageRange, splitChapterTitle, type Chapter } from "./courses";

describe("splitChapterTitle", () => {
  it("separates the chapter number from its title", () => {
    expect(splitChapterTitle("Chapter 3 Biopsychology")).toEqual({ number: "3", title: "Biopsychology" });
    expect(splitChapterTitle("Chapter IV: Cell Structure")).toEqual({ number: "IV", title: "Cell Structure" });
  });

  it("leaves other titles alone", () => {
    expect(splitChapterTitle("1 Cells")).toEqual({ number: null, title: "1 Cells" });
    expect(splitChapterTitle("Chapter 7")).toEqual({ number: null, title: "Chapter 7" });
  });
});

describe("pageRange", () => {
  const chapter = (start: number | null, end: number | null): Chapter => ({
    id: "1",
    title: "Chapter 1",
    page_start: start,
    page_end: end,
    covered_at: null,
  });

  it("describes single pages and ranges", () => {
    expect(pageRange(chapter(19, 46))).toBe("pages 19–46");
    expect(pageRange(chapter(7, 7))).toBe("page 7");
    expect(pageRange(chapter(null, null))).toBeNull();
  });
});
