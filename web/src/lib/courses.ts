/** Types for the course endpoints (see backend `api/routes/courses.py`). */

export type CourseSummary = { id: string; title: string; chapters: number; covered: number };

export type Chapter = {
  id: string;
  title: string;
  page_start: number | null;
  page_end: number | null;
  covered_at: string | null;
  /** Kept when a chapter is unmarked. */
  cards: number;
  /** Only while covered: "pending" until its cards are made. */
  cards_status: "pending" | "ready" | "failed" | null;
};

export type Textbook = { material_id: string; title: string; chapters: Chapter[] };

export type Material = {
  id: string;
  title: string;
  kind: "textbook" | "slides";
  status: "uploading" | "queued" | "processing" | "ready" | "failed";
};

export type Course = { id: string; title: string; textbooks: Textbook[]; materials: Material[] };

export type Coverage = { section_id: string; covered_at: string };

/** "Chapter 3 Biopsychology" → { number: "3", title: "Biopsychology" }, for a tidy list. */
export function splitChapterTitle(title: string): { number: string | null; title: string } {
  const match = /^chapter\s+(\d+|[IVXLC]+)\b[\s.:–-]*(.*)$/i.exec(title.trim());
  if (!match || !match[2]) return { number: null, title: title.trim() };
  return { number: match[1], title: match[2] };
}

export function pageRange(chapter: Chapter): string | null {
  if (chapter.page_start === null) return null;
  if (chapter.page_end === null || chapter.page_end === chapter.page_start) {
    return `page ${chapter.page_start}`;
  }
  return `pages ${chapter.page_start}–${chapter.page_end}`;
}

/** The second line of a chapter row: when it was covered and how its cards are doing. */
export function chapterNote(chapter: Chapter, coveredOn: (iso: string) => string): string | null {
  const cards = `${chapter.cards} ${chapter.cards === 1 ? "card" : "cards"}`;
  if (!chapter.covered_at) {
    const pages = pageRange(chapter);
    return chapter.cards ? [pages, cards].filter(Boolean).join(" · ") : pages;
  }
  const covered = `Covered on ${coveredOn(chapter.covered_at)}`;
  switch (chapter.cards_status) {
    case "ready":
      return `${covered} · ${cards}`;
    case "failed":
      return `${covered} · Its cards couldn't be made. Unmark it and mark it again to retry.`;
    default:
      return `${covered} · Making cards…`;
  }
}
