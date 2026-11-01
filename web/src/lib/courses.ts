/** Types for the course endpoints (see backend `api/routes/courses.py`). */

export type CourseSummary = {
  id: string;
  title: string;
  chapters: number;
  covered: number;
  /** Whose course it is, so the admin page can list one person's courses. */
  owner_id: string;
};

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
  /** While pending: cards drafted so far. Repeats are dropped at the end, so it can end a little lower. */
  cards_drafted: number;
};

export type Textbook = { material_id: string; title: string; chapters: Chapter[] };

export type Material = {
  id: string;
  title: string;
  kind: "textbook" | "slides";
  status: "uploading" | "queued" | "processing" | "ready" | "failed";
  /** While processing: the step it's on. */
  stage?: "parsing" | "describing" | "indexing" | null;
  /** Why it couldn't be read, once failed. */
  failure?: "no_text" | "protected" | "damaged" | "stalled" | "unknown" | null;
  /** A PDF, which opens in the browser. PowerPoint files can't. */
  viewable: boolean;
};

/** Which step a material being read is on. A textbook takes minutes, so it says so. */
export function readingText(material: Pick<Material, "kind" | "stage">): string {
  switch (material.stage) {
    case "describing":
      return "Looking at its figures and diagrams. You can leave this page.";
    case "indexing":
      return "Almost ready. You can leave this page.";
    default:
      return material.kind === "textbook"
        ? "Reading the pages. A textbook takes a few minutes; you can leave this page."
        : "Reading the slides. You can leave this page.";
  }
}

/** What went wrong reading a failed material, and what to do about it. */
export function failureText(material: Pick<Material, "failure" | "viewable">): string {
  switch (material.failure) {
    case "no_text":
      return "Engram couldn't find any text in this file. If it's scanned pages or photos, add a copy where you can select the text.";
    case "protected":
      return "This file is password-protected. Save a copy without the password and add that instead.";
    case "damaged":
      return "This file seems to be damaged, or isn't really a PDF or PowerPoint. Open it, save a new copy and add that.";
    case "stalled":
      return "This file took too long to read. Try splitting it into smaller files.";
    default:
      return material.viewable
        ? "Something went wrong reading this file. Remove it and add it again."
        : "Something went wrong reading this file. Remove it and try a PDF version.";
  }
}

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
      return `${covered} · Its cards couldn't be made.`;
    default:
      return chapter.cards_drafted > 0
        ? `${covered} · ${chapter.cards_drafted} ${chapter.cards_drafted === 1 ? "card" : "cards"} so far…`
        : `${covered} · Making cards…`;
  }
}
