import { describe, expect, it } from "vitest";

import { chapterNote, pageRange, splitChapterTitle, type Chapter } from "./courses";

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
    cards: 0,
    cards_status: null,
    cards_drafted: 0,
  });

  it("describes single pages and ranges", () => {
    expect(pageRange(chapter(19, 46))).toBe("pages 19–46");
    expect(pageRange(chapter(7, 7))).toBe("page 7");
    expect(pageRange(chapter(null, null))).toBeNull();
  });
});

describe("chapterNote", () => {
  const base: Chapter = {
    id: "1",
    title: "Chapter 1",
    page_start: 19,
    page_end: 46,
    covered_at: null,
    cards: 0,
    cards_status: null,
    cards_drafted: 0,
  };
  const on = () => "27 October";

  it("shows pages, and cards kept from an earlier mark", () => {
    expect(chapterNote(base, on)).toBe("pages 19–46");
    expect(chapterNote({ ...base, cards: 1 }, on)).toBe("pages 19–46 · 1 card");
  });

  it("follows a covered chapter's cards being made", () => {
    const covered = { ...base, covered_at: "2026-10-27T10:00:00Z" };
    expect(chapterNote({ ...covered, cards_status: "pending" }, on)).toBe("Covered on 27 October · Making cards…");
    expect(chapterNote({ ...covered, cards_status: "pending", cards_drafted: 1 }, on)).toBe(
      "Covered on 27 October · 1 card so far…",
    );
    expect(chapterNote({ ...covered, cards_status: "pending", cards_drafted: 14 }, on)).toBe(
      "Covered on 27 October · 14 cards so far…",
    );
    expect(chapterNote({ ...covered, cards_status: "ready", cards: 24 }, on)).toBe("Covered on 27 October · 24 cards");
    expect(chapterNote({ ...covered, cards_status: "failed" }, on)).toMatch(/couldn't be made/);
  });
});
