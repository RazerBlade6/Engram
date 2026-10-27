import { describe, expect, it } from "vitest";

import { choiceRating, comesBackToday, passageParts, whenLabel, type ReviewCard } from "./review";

const now = new Date("2026-10-27T12:00:00Z");
const later = (ms: number) => new Date(now.getTime() + ms).toISOString();
const MIN = 60 * 1000;
const DAY = 24 * 60 * MIN;

describe("whenLabel", () => {
  it("says when a card comes back, without numbers that look precise", () => {
    expect(whenLabel(later(10 * MIN), now)).toBe("see it again soon");
    expect(whenLabel(later(DAY), now)).toBe("tomorrow");
    expect(whenLabel(later(3 * DAY), now)).toBe("in 3 days");
    expect(whenLabel(later(21 * DAY), now)).toBe("in 3 weeks");
    expect(whenLabel(later(120 * DAY), now)).toBe("in 4 months");
    expect(whenLabel(later(400 * DAY), now)).toBe("in a year");
  });
});

describe("comesBackToday", () => {
  it("brings back cards in their first short steps", () => {
    expect(comesBackToday(later(10 * MIN), now)).toBe(true);
    expect(comesBackToday(later(2 * DAY), now)).toBe(false);
  });
});

describe("choiceRating", () => {
  it("rates a multiple-choice answer by whether it was right", () => {
    const card = { answer: "Dendrites" } as ReviewCard;
    expect(choiceRating(card, "Dendrites")).toBe(3);
    expect(choiceRating(card, "Axon")).toBe(1);
  });
});

describe("passageParts", () => {
  it("splits the passage around the quote", () => {
    const source = { book: "b", heading_path: [], page: 1, passage: "One. Two three. Four.", highlight: [5, 15] as [number, number] };
    expect(passageParts(source)).toEqual({ before: "One. ", marked: "Two three.", after: " Four." });
    expect(passageParts({ ...source, highlight: null })).toEqual({ before: source.passage, marked: "", after: "" });
  });
});
