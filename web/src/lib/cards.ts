/** Types for a chapter's cards (see backend `api/routes/courses.py`). */

export type CardSource = {
  quote: string;
  heading_path: string[];
  page: number | null;
};

export type Card = {
  id: string;
  kind: "basic" | "cloze" | "mcq";
  concept: string;
  prompt: string;
  answer: string;
  choices: string[];
  sources: CardSource[];
};

export const KIND_LABEL: Record<Card["kind"], string> = {
  basic: "Question",
  cloze: "Fill in the blank",
  mcq: "Multiple choice",
};

/** "The {{nucleus}} stores DNA." → text and hidden parts, in order. */
export function clozeParts(prompt: string): { text: string; hidden: boolean }[] {
  return prompt
    .split(/(\{\{.+?\}\})/)
    .filter(Boolean)
    .map((part) => {
      const match = /^\{\{(.+)\}\}$/.exec(part);
      return match ? { text: match[1], hidden: true } : { text: part, hidden: false };
    });
}

/** Where a card comes from, for a citation: "Section 1.2, page 23". */
export function sourceLabel(source: CardSource): string {
  const heading = source.heading_path.at(-1);
  const page = source.page === null ? null : `page ${source.page}`;
  return [heading, page].filter(Boolean).join(", ");
}
