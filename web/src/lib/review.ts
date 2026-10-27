/** Types and helpers for reviewing (see backend `api/routes/review.py`). */

export type Rating = 1 | 2 | 3 | 4;

export type ReviewSource = {
  book: string;
  heading_path: string[];
  page: number | null;
  passage: string;
  highlight: [number, number] | null;
};

export type ReviewCard = {
  id: string;
  kind: "basic" | "cloze" | "mcq";
  prompt: string;
  answer: string;
  choices: string[];
  course: string;
  chapter: string | null;
  new: boolean;
  /** When the card would next be due for each rating. */
  next: Record<Rating, string>;
  source: ReviewSource | null;
};

/** How flashcards and multiple choice are arranged; set per student by an admin. */
export type ReviewOrder = "mixed" | "blocked" | "separate";
/** With "separate", flashcards are the "review" and multiple choice the "quiz". */
export type ReviewSession = "review" | "quiz";

export type SessionSummary = { session: ReviewSession; cards: number; minutes: number; courses: string[] };
export type ReviewSummary = { order: ReviewOrder; sessions: SessionSummary[] };
export type ReviewQueue = { order: ReviewOrder; cards: ReviewCard[] };

export const ORDER_LABEL: Record<ReviewOrder, string> = {
  mixed: "Mixed: card types interleaved",
  blocked: "Blocked: flashcards, then multiple choice",
  separate: "Separate: a Review and a Quiz session",
};

export type Reviewed = { due: string; next: Record<Rating, string> };

export const RATINGS: { rating: Rating; label: string; tone: string }[] = [
  { rating: 1, label: "Forgot", tone: "text-danger" },
  { rating: 2, label: "Hard", tone: "" },
  { rating: 3, label: "Got it", tone: "" },
  { rating: 4, label: "Easy", tone: "text-success" },
];

export const FLAG_REASONS = [
  { reason: "wrong", label: "The answer is wrong", detail: "It doesn't match the course material" },
  { reason: "confusing", label: "It's confusing", detail: "The question is unclear or has more than one answer" },
  { reason: "not_useful", label: "It's not useful", detail: "Too obvious, or not something I need to know" },
] as const;

/** Cards due again within this long come back in the same session (matches the API). */
const LEARN_AHEAD_MS = 20 * 60 * 1000;

/** "see it again soon", "tomorrow", "in 3 days": when a rating brings the card back. */
export function whenLabel(due: string, now: Date): string {
  const ms = new Date(due).getTime() - now.getTime();
  if (ms < 60 * 60 * 1000) return "see it again soon";
  const days = Math.round(ms / (24 * 60 * 60 * 1000));
  if (days <= 1) return "tomorrow";
  if (days < 14) return `in ${days} days`;
  if (days < 60) return `in ${Math.round(days / 7)} weeks`;
  if (days < 365) return `in ${Math.round(days / 30)} months`;
  const years = Math.round(days / 365);
  return years === 1 ? "in a year" : `in ${years} years`;
}

/** Whether a card just rated comes back before the session ends. */
export function comesBackToday(due: string, now: Date): boolean {
  return new Date(due).getTime() - now.getTime() < LEARN_AHEAD_MS;
}

/**
 * Puts a card that's still being learned back in the session. In the blocked order it goes
 * to the end of its own block, so flashcards stay ahead of multiple choice.
 */
export function requeue(queue: ReviewCard[], card: ReviewCard, order: ReviewOrder): ReviewCard[] {
  if (order !== "blocked" || card.kind === "mcq") return [...queue, card];
  const quiz = queue.findIndex((c) => c.kind === "mcq");
  if (quiz === -1) return [...queue, card];
  return [...queue.slice(0, quiz), card, ...queue.slice(quiz)];
}

/** A multiple-choice answer rates itself: right is "Got it", wrong is "Forgot". */
export function choiceRating(card: ReviewCard, choice: string): Rating {
  return choice === card.answer ? 3 : 1;
}

/** The passage split around its highlighted quote, for display. */
export function passageParts(source: ReviewSource): { before: string; marked: string; after: string } {
  if (!source.highlight) return { before: source.passage, marked: "", after: "" };
  const [start, end] = source.highlight;
  return {
    before: source.passage.slice(0, start),
    marked: source.passage.slice(start, end),
    after: source.passage.slice(end),
  };
}
