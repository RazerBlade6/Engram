import { describe, expect, it } from "vitest";

import { chaptersLabel, courseColors, daysBetween, monthWeeks, untilLabel, upcoming, type CourseDate } from "./calendar";

const date = (on: string, title = "Midterm"): CourseDate => ({
  id: title + on,
  course_id: "c",
  course: "Psychology",
  kind: "exam",
  title,
  on,
  chapters: [],
});

describe("monthWeeks", () => {
  it("fills whole weeks from the first day of the week", () => {
    // November 2026 starts on a Sunday.
    const weeks = monthWeeks(2026, 10);
    expect(weeks[0]).toEqual([
      "2026-10-26",
      "2026-10-27",
      "2026-10-28",
      "2026-10-29",
      "2026-10-30",
      "2026-10-31",
      "2026-11-01",
    ]);
    expect(weeks.at(-1)?.at(-1)).toBe("2026-12-06");
    expect(weeks).toHaveLength(6);
  });

  it("starts weeks on Sunday where the locale does", () => {
    const weeks = monthWeeks(2026, 10, 7);
    expect(weeks[0][0]).toBe("2026-11-01");
    expect(weeks).toHaveLength(5);
  });
});

describe("daysBetween", () => {
  it("counts whole days across a daylight-saving change", () => {
    expect(daysBetween("2026-10-24", "2026-10-26")).toBe(2);
    expect(daysBetween("2026-12-31", "2027-01-01")).toBe(1);
  });
});

describe("upcoming", () => {
  it("keeps today and later, earliest first", () => {
    const dates = [date("2026-11-13"), date("2026-10-20", "Quiz"), date("2026-10-27", "Essay")];
    expect(upcoming(dates, "2026-10-27").map((d) => d.title)).toEqual(["Essay", "Midterm"]);
  });
});

describe("untilLabel", () => {
  it("says how far off a date is", () => {
    expect(untilLabel("2026-10-27", "2026-10-27")).toBe("today");
    expect(untilLabel("2026-10-28", "2026-10-27")).toBe("tomorrow");
    expect(untilLabel("2026-11-04", "2026-10-27")).toBe("in 8 days");
    expect(untilLabel("2026-11-13", "2026-10-27")).toBe("in 2 weeks");
    expect(untilLabel("2026-10-25", "2026-10-27")).toBe("2 days ago");
  });
});

describe("courseColors", () => {
  it("gives each course its own color, cycling after six", () => {
    const colors = courseColors(Array.from({ length: 7 }, (_, i) => ({ id: `c${i}` })));
    expect(colors.get("c0")).toBe("var(--course-1)");
    expect(colors.get("c5")).toBe("var(--course-6)");
    expect(colors.get("c6")).toBe("var(--course-1)");
  });
});

describe("chaptersLabel", () => {
  const ch = (...titles: string[]) => titles.map((title) => ({ title }));

  it("names the chapters a date covers briefly", () => {
    expect(chaptersLabel([])).toBeNull();
    expect(chaptersLabel(ch("Chapter 3 Biopsychology"))).toBe("Chapter 3");
    expect(chaptersLabel(ch("Chapter 1 Intro", "Chapter 2 Research", "Chapter 3 Bio", "Chapter 5 Senses"))).toBe(
      "Chapters 1–3, 5",
    );
    expect(chaptersLabel(ch("Chapter 3 A", "Chapter 4 B"))).toBe("Chapters 3, 4");
    expect(chaptersLabel(ch("Cells"))).toBe("Cells");
    expect(chaptersLabel(ch("Cells", "Genetics"))).toBe("2 chapters");
  });
});
