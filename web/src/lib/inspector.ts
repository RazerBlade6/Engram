/** Types and helpers for the ingestion inspector (see backend `api/routes/inspector.py`). */

export type MaterialSummary = {
  id: string;
  title: string;
  kind: "textbook" | "slides";
  status: "uploading" | "queued" | "processing" | "ready" | "failed";
  error: string | null;
  page_count: number | null;
  course: string;
  created_at: string;
  sections: number;
  figures: number;
  chunks: number;
  /** Who uploaded it. Not sent by the API yet; the admin page shows a dash until it is. */
  uploaded_by?: string | null;
  /** Whose course it belongs to. Not sent by the API yet, like `uploaded_by`. */
  owner?: string | null;
};

export type Section = {
  id: string;
  parent_id: string | null;
  ordinal: number;
  level: number;
  title: string;
  page_start: number | null;
  page_end: number | null;
};

export type PageStats = { page: number; text: number; tables: number; figures: number };

export type Inspection = {
  material: MaterialSummary;
  preview: boolean;
  sections: Section[];
  pages: PageStats[];
};

/** [left, top, right, bottom] in PDF points from the page's top-left corner. */
export type BBox = [number, number, number, number];

export type ChunkBox = {
  chunk_id: string;
  ordinal: number;
  kind: "text" | "table" | "slide";
  heading_path: string[];
  content: string;
  bbox: BBox;
  part: number;
  parts: number;
};

export type FigureBox = {
  id: string;
  ordinal: number;
  bbox: BBox;
  caption: string | null;
  description: string | null;
  labels: string[];
  described_by: string | null;
};

export type Page = {
  page: number;
  width: number | null;
  height: number | null;
  chunks: ChunkBox[];
  figures: FigureBox[];
};

/** Positions a box over the page image, in percentages so it scales with the image. */
export function boxStyle(bbox: BBox, width: number, height: number) {
  const [left, top, right, bottom] = bbox;
  return {
    left: `${(left / width) * 100}%`,
    top: `${(top / height) * 100}%`,
    width: `${((right - left) / width) * 100}%`,
    height: `${((bottom - top) / height) * 100}%`,
  };
}

/** Sections whose page range includes `page`, outermost first. */
export function sectionsOnPage(sections: Section[], page: number): Section[] {
  return sections.filter((s) => s.page_start !== null && s.page_start <= page && page <= (s.page_end ?? s.page_start));
}

/** Pages where nothing was extracted: often blank, sometimes a missed scan or a broken parse. */
export function emptyPages(pageCount: number, pages: PageStats[]): number[] {
  const seen = new Set(pages.map((p) => p.page));
  return Array.from({ length: pageCount }, (_, i) => i + 1).filter((p) => !seen.has(p));
}

/** Collapses runs of consecutive pages: [1, 2, 3, 7, 9, 10] → "1–3, 7, 9–10". */
export function pageRanges(pages: number[]): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  for (const page of pages) {
    const last = ranges.at(-1);
    if (last && page === last.end + 1) last.end = page;
    else ranges.push({ start: page, end: page });
  }
  return ranges;
}
