/** Types and helpers for important dates (see backend `api/routes/dates.py`). */

import { splitChapterTitle } from "./courses";

export type DateKind = "exam" | "quiz" | "deadline";

export type DateChapter = { id: string; title: string };

/** `on` is a calendar day, "2026-11-13", with no time or time zone. Chapters are in book order. */
export type CourseDate = {
  id: string;
  course_id: string;
  course: string;
  kind: DateKind;
  title: string;
  on: string;
  chapters: DateChapter[];
};

/** `chapters` are the section ids of the chapters it covers. */
export type NewDate = { kind: DateKind; title: string; on: string; chapters: string[] };

export const KIND_LABEL: Record<DateKind, string> = { exam: "Exam", quiz: "Quiz", deadline: "Deadline" };

/** Placeholders for the quick-add "what" field. */
export const KIND_EXAMPLE: Record<DateKind, string> = { exam: "Midterm", quiz: "Quiz 3", deadline: "Essay 2" };

const COURSE_COLORS = 6;

/** Each course's color, as a CSS variable, by its place in the course list. */
export function courseColors(courses: { id: string }[]): Map<string, string> {
  return new Map(courses.map((c, i) => [c.id, `var(--course-${(i % COURSE_COLORS) + 1})`]));
}

/** The student's local today as "2026-10-27". */
export function isoDay(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** "2026-11-13" as local midnight (`new Date("2026-11-13")` would be UTC midnight). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Whole days from `from` to `to`, unaffected by daylight-saving changes in between. */
export function daysBetween(from: string, to: string): number {
  const utc = (iso: string) => {
    const [y, m, d] = iso.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

/** Dates from today on, in order. ISO days compare correctly as strings. */
export function upcoming(dates: CourseDate[], today: string): CourseDate[] {
  return dates.filter((d) => d.on >= today).sort((a, b) => a.on.localeCompare(b.on));
}

/** "today", "tomorrow", "in 5 days", "in 3 weeks". */
export function untilLabel(on: string, today: string): string {
  const days = daysBetween(today, on);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days < 0) return days === -1 ? "yesterday" : `${-days} days ago`;
  if (days < 14) return `in ${days} days`;
  return `in ${Math.round(days / 7)} weeks`;
}

/**
 * Dates are always written day first (D54), whatever the browser's locale: a student on a US
 * locale was confused by month-first dates.
 */
const DAY_FIRST = "en-GB";

/** The parts of a day joined by spaces, without the commas some formats add: "Fri 8 Jan 2027". */
function written(on: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(DAY_FIRST, options)
    .formatToParts(parseDay(on))
    .filter((part) => part.type !== "literal")
    .map((part) => part.value)
    .join(" ");
}

/** "Fri 13 Nov", with the year only when it isn't this year's. */
export function dayLabel(on: string, today: string): string {
  const sameYear = on.slice(0, 4) === today.slice(0, 4);
  return written(on, { weekday: "short", day: "numeric", month: "short", year: sameYear ? undefined : "numeric" });
}

/** "Friday 13 November 2026": confirms in words which day a typed date means. */
export function longDayLabel(on: string): string {
  return written(on, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

// Matches the API's range: wide enough for any course, narrow enough to catch a mistyped year.
export const FIRST_DAY = "2000-01-01";
export const LAST_DAY = "2100-12-31";

/**
 * A typed date, day/month/year, as an ISO day: "13/11/2026", "13-11-26" and "13.11.2026" all
 * give "2026-11-13". Null if it isn't a real day in range.
 */
export function parseTypedDay(text: string): string | null {
  const match = /^\s*(\d{1,2})\s*[/.\- ]\s*(\d{1,2})\s*[/.\- ]\s*(\d{2}|\d{4})\s*$/.exec(text);
  if (!match) return null;
  const [day, month] = [Number(match[1]), Number(match[2])];
  const year = match[3].length === 2 ? 2000 + Number(match[3]) : Number(match[3]);
  const date = new Date(year, month - 1, day);
  // new Date rolls 31/02 over into March; a real day comes back unchanged.
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  const iso = isoDay(date);
  return iso >= FIRST_DAY && iso <= LAST_DAY ? iso : null;
}

/** "2026-11-13" as "13/11/2026", for the date field. */
export function typedDay(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

/**
 * The weeks shown for a month, as ISO days, starting on `firstDay` (1 is Monday, 7 is Sunday).
 * Days from the months either side fill the first and last weeks.
 */
export function monthWeeks(year: number, month: number, firstDay = 1): string[][] {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() - (firstDay % 7) + 7) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const weeks = Math.ceil((lead + daysInMonth) / 7);
  return Array.from({ length: weeks }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => isoDay(new Date(year, month, 1 - lead + w * 7 + d))),
  );
}

/** The locale's first day of the week, where the browser says; Monday otherwise. */
export function localFirstDay(): number {
  try {
    const locale = new Intl.Locale(navigator.language) as Intl.Locale & {
      getWeekInfo?: () => { firstDay: number };
      weekInfo?: { firstDay: number };
    };
    return locale.getWeekInfo?.().firstDay ?? locale.weekInfo?.firstDay ?? 1;
  } catch {
    return 1;
  }
}

/** "Chapter 3", "Chapters 1–3, 5", or, for chapters without numbers, "2 chapters". */
export function chaptersLabel(chapters: { title: string }[]): string | null {
  if (!chapters.length) return null;
  const numbers = chapters.map((c) => Number(splitChapterTitle(c.title).number));
  if (numbers.some((n) => !Number.isInteger(n) || n <= 0)) {
    return chapters.length === 1 ? chapters[0].title : `${chapters.length} chapters`;
  }
  if (numbers.length === 1) return `Chapter ${numbers[0]}`;
  const ranges: string[] = [];
  const sorted = [...new Set(numbers)].sort((a, b) => a - b);
  for (let i = 0; i < sorted.length; i++) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    ranges.push(j - i >= 2 ? `${sorted[i]}–${sorted[j]}` : sorted.slice(i, j + 1).join(", "));
    i = j;
  }
  return `Chapters ${ranges.join(", ")}`;
}
